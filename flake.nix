{
  description = "NixOS deployment tool with parallel deploys and an ANSI TUI";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs =
    { nixpkgs, ... }:
    let
      eachSystem = nixpkgs.lib.genAttrs [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
    in
    {
      packages = eachSystem (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.python313Packages.buildPythonApplication {
            pname = "snip";
            version = "0.1.0";
            src = ./.;
            pyproject = true;
            build-system = [ pkgs.python313Packages.hatchling ];
          };
        }
      );
    };
}
