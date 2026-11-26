# Hardware tools in Docker Compose

Copy the [hardware asset directory](../assets/hardware/) to `tools/hardware/` in the gadget repository. The compose file mounts the gadget root at `/project`. From the gadget root:

```sh
export HOST_UID="$(id -u)" HOST_GID="$(id -g)"
hw() { docker compose -f tools/hardware/compose.yaml "$@"; }
hw run --rm kicad kicad-cli version
```

These are one-shot commands. The first use downloads the selected image or builds the selected Dockerfile. Runtime commands have networking disabled. KiCad, KiCadRoutingTools and CadQuery use Linux amd64 (emulated on Apple Silicon). Freerouting selects its native amd64 or arm64 image. Keep the Dockerfiles and compose file with the gadget's toolchain record. Record the built image IDs when exact reproduction matters because transitive OS and Python packages can change.

## KiCad and routing

Keep the `.kicad_pro`, custom libraries, and 3D models accessible at project-relative paths. The KiCad service initializes stock symbol and footprint tables. It can run either `kicad-cli` or Python scripts using `pcbnew`. Replace the example filenames with the project's paths. Create the output directories first.

```sh
mkdir -p reports
hw run --rm kicad kicad-cli sch erc --format json --exit-code-violations -o reports/erc.json pcb/gadget.kicad_sch
hw run --rm kicad kicad-cli pcb drc --schematic-parity --format json --exit-code-violations -o reports/drc.json pcb/gadget.kicad_pcb
```

For autorouting, copy the placement, matching project rules, schematic and libraries into a fresh trial directory. Keep the accepted placement intact. Choose either route:

- **KiCadRoutingTools** reads and writes native board files. Run `hw build krt` to fetch the pinned upstream source, Python requirements and checksum-verified Rust engine. Run `hw run --rm krt py_router/route.py --help` for the available controls. For example, `hw run --rm krt py_router/route.py /project/trial/input.kicad_pcb /project/trial/output.kicad_pcb --nets SDA SCL --layers F.Cu B.Cu` targets those exact nets and layers. Supply the actual project net names, layer set, widths and clearances. Use `py_router/qfn_fanout.py` when package breakout calls for it. The pilot used targeted fanout and native routing. Its net order, via costs and mechanical constraints belong to that board.
- **Freerouting** uses Specctra exchange. In the KiCad service use `pcbnew.ExportSpecctraDSN(board, dsn_path)`, then run `hw run --rm freerouting -de /project/trial/input.dsn -do /project/trial/result.ses -mp 50`. Import the fresh result into the same board revision with `pcbnew.ImportSpecctraSES(board, ses_path)`, check its return value, and save a separate board via `pcbnew.SaveBoard`. Use a bounded run and a fresh output path for each attempt.

Refill zones on the resulting board, run DRC with its matching project settings and inspect the unconnected-items list and the critical routes. For enclosure work, export the populated board with `kicad-cli pcb export step` and inspect any missing models before relying on a fit measurement. [KiCad CLI](https://docs.kicad.org/10.0/en/cli/cli.html)

## Enclosure CAD

For a CadQuery project, run `hw build cad` to install CadQuery 2.5.2, its OCP 7.7.2 geometry kernel, and the VTK 9.3.1 OSMesa wheel for offscreen renders. Run the project's editable model and fit checks with `hw run --rm cad enclosure/model.py`. Its outputs land in the mounted project. Use STEP for solid exchange, STL for a printable mesh, and a rendered PNG for the review board. Reimport the STEP and check the important dimensions or clearances. A model that renders through VTK can use `vtkRenderWindow.SetOffScreenRendering(1)` without a display server. Other CAD backends can use their native project workflow.
