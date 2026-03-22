{
  inputs = {
    nixpkgs.url = "git+https://github.com/NixOS/nixpkgs?ref=nixos-24.11";
    nixpkgs-unstable.url = "git+https://github.com/NixOS/nixpkgs?ref=nixpkgs-unstable";
  };

  outputs = { self, nixpkgs, nixpkgs-unstable }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          unstable = nixpkgs-unstable.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python312
              pkgs.uv
              pkgs.nodejs_22
              pkgs.docker-compose
              unstable.supabase-cli
            ];
            shellHook = ''
              export UV_PYTHON=${pkgs.python312}/bin/python3.12
            '';
          };
        });
    };
}
