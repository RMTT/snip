import os
import subprocess
import time
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).parent
KEYS_DIR = E2E_DIR / "keys"


@pytest.fixture(scope="module")
def qemu_vm():
    """Builds and runs a minimal NixOS VM, yielding once SSH is available."""
    # 1. Build the VM script
    print("\nBuilding NixOS VM for e2e tests...")
    build_cmd = [
        "nix",
        "build",
        ".#nixosConfigurations.test-vm.config.system.build.vm",
        "--print-build-logs",
    ]
    try:
        subprocess.run(build_cmd, cwd=E2E_DIR, check=True)
    except FileNotFoundError:
        pytest.skip("nix is not available. Skipping E2E tests.")
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to build test VM: {e}")

    # 2. Start the VM
    vm_script = E2E_DIR / "result" / "bin" / "run-test-vm-vm"
    if not vm_script.exists():
        pytest.fail(f"VM script not found at {vm_script}")

    print("Starting QEMU VM...")
    env = os.environ.copy()
    env["QEMU_NET_OPTS"] = "hostfwd=tcp::2222-:22"

    # We use preexec_fn=os.setsid to be able to kill the process group later
    process = subprocess.Popen(
        [str(vm_script)],
        cwd=E2E_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    # 3. Wait for SSH to be available
    ssh_cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=1",
        "-i",
        str(KEYS_DIR / "id_ed25519"),
        "-p",
        "2222",
        "snip@localhost",
        "echo",
        "ready",
    ]

    max_retries = 60
    ready = False
    for i in range(max_retries):
        try:
            res = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and "ready" in res.stdout:
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not ready:
        os.killpg(os.getpgid(process.pid), 9)
        pytest.fail("VM did not become ready within timeout.")

    print("VM is ready!")

    yield

    # 4. Teardown
    print("\nStopping QEMU VM...")
    try:
        os.killpg(os.getpgid(process.pid), 9)
        process.wait(timeout=5)
    except Exception as e:
        print(f"Error during VM teardown: {e}")


def test_deploy_e2e(qemu_vm):
    """Test deploying a minimal NixOS configuration to the QEMU VM."""
    snip_cmd = ["uv", "run", "snip", "deploy"]

    # Run the snip deployment
    print("Running snip deploy...")
    res = subprocess.run(snip_cmd, cwd=E2E_DIR, capture_output=True, text=True)

    print("stdout:", res.stdout)
    if res.stderr:
        print("stderr:", res.stderr)

    assert res.returncode == 0, f"snip deploy failed with code {res.returncode}"

    # Verify the deployment by SSHing into the VM and checking the result
    # We added curl to the environment.systemPackages in our snip config,
    # let's make sure it's accessible and functioning in the new profile.
    verify_cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "BatchMode=yes",
        "-i",
        str(KEYS_DIR / "id_ed25519"),
        "-p",
        "2222",
        "snip@localhost",
        "curl",
        "--version",
    ]

    verify_res = subprocess.run(verify_cmd, capture_output=True, text=True)

    assert verify_res.returncode == 0, (
        "Failed to verify the deployment (curl not found)"
    )
    assert "curl" in verify_res.stdout, "curl command output did not contain 'curl'"
