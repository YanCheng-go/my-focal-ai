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
              # uv from unstable: stable nixos-24.11 ships 0.4.30, which writes
              # an older lockfile format (no revision/upload-time) and churns
              # uv.lock on every run. unstable matches the committed lock format.
              unstable.uv
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
