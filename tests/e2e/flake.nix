{
  description = "Minimal test flake for snip e2e tests";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs = { self, nixpkgs }: {
    nixosConfigurations.test-vm = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        ({ config, pkgs, ... }: {
          boot.loader.grub.enable = false;
          fileSystems."/" = { device = "/dev/vda"; fsType = "ext4"; };

          # Minimal profile
          environment.systemPackages = with pkgs; [ vim curl ];

          # Enable sshd and set up the snip user
          services.openssh.enable = true;

          users.users.snip = {
            isNormalUser = true;
            extraGroups = [ "wheel" ];
            openssh.authorizedKeys.keys = [
              (builtins.readFile ./keys/id_ed25519.pub)
            ];
          };

          # Passwordless sudo for snip
          security.sudo.wheelNeedsPassword = false;

          # We don't care about state version in the test
          system.stateVersion = "24.05";
        })
      ];
    };

    snip = {
      defaults.nodes = {
        user = "snip";
        port = 2222;
        sshOptions = [
          "IdentityFile=${toString ./keys/id_ed25519}"
          "StrictHostKeyChecking=no"
          "UserKnownHostsFile=/dev/null"
        ];
      };

      nodes = {
        test-vm = {
          host = "localhost";
          config = "nixosConfigurations.test-vm";
        };
      };
    };
  };
}
