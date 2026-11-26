# Build and check firmware in Docker

Start in the firmware project, including for the first proof of concept. Reuse its Dockerfile and verification command if present. Otherwise copy the [starter Dockerfile](../assets/Dockerfile.firmware) into the firmware directory and add a project-owned `verify.sh`. The host needs Docker with BuildKit. Install the compiler, SDK, package tools, simulator and any browser bundler in the Linux toolchain image. Choose a supported Linux host architecture for those tools independently of the MCU architecture.

**Prepare the toolchain.** Set the starter's `TOOLCHAIN_IMAGE` to a verified image containing the project dependencies. Pin the base by digest and record the platform. If the SDK image needs extra libraries, add a dependency stage before `verify`, copy the project's manifests and lockfiles there, install the pinned dependencies, and derive `verify` from that stage. For example, a PlatformIO/Arduino proxy with a JavaScript simulator can install PlatformIO, run `pio pkg install -e uno` and `npm ci` during preparation. Select the actual project environment in place of `uno`. Keep host SDK caches, build output, device credentials and unrelated files outside the build context with a project `.dockerignore`.

**Provide one verification command.** Start `verify.sh` with `set -eu`. Build for the named board, run applicable tests, and when local simulation is in scope, launch the headless simulator **with the just-built binary** and check an observable outcome. Make any failure exit nonzero. Copy the binary, test reports and optional browser demo or display captures to `$FIRMWARE_OUT`. Keep the checked-in source and exported artifacts in separate directories. Exercise this path from clean inputs before calling the firmware build verified.

From the firmware build context, set `TOOLCHAIN_IMAGE` to the pinned image reference and `ARTIFACT_DIR` to a fresh directory outside that context. Run:

```sh
docker buildx build --file Dockerfile.firmware \
  --build-arg "TOOLCHAIN_IMAGE=${TOOLCHAIN_IMAGE:?set the toolchain image}" \
  --target artifacts --no-cache-filter verify \
  --output "type=local,dest=${ARTIFACT_DIR:?set a fresh output directory}" .
```

The verification stage runs offline. Dependency preparation can use the network. The export contains only the selected files and a failed check prevents the export from completing. Record the exact invocation, image and architecture, dependency locks, output hashes and check results. Keep a browser demo tied to that same build so it can be opened on the host. [Docker artifact export](https://docs.docker.com/build/exporters/local-tar/)

**Serve an interactive browser demo.** Copy [compose.yaml](../assets/compose.yaml) beside the starter Dockerfile when the project has a browser simulator. Have `verify.sh` write its launch page at `$FIRMWARE_OUT/preview/index.html`, with the same tested firmware embedded or copied alongside its runtime assets. Everything in `preview/` is served. Keep reports and other build outputs in the parent output directory. Export `TOOLCHAIN_IMAGE` in the shell or set it in the project's local Compose `.env`, then run:

```sh
docker compose up --build -d
```

Open `http://127.0.0.1:8786` and exercise a control. Set `SIM_PORT` to an available port when running several demos. Stop the project with `docker compose down`. Firmware without a browser interface uses the existing `artifacts` target directly.

**Keep the evidence scoped to the target.** For example, the USB key's three buttons and OLED can be exercised with an Uno build and AVR8js while its production target is an STM32U545. Label the proxy binary and reports with their target and keep them out of a factory programming bundle for the STM32. If using Wokwi's cloud service, run the client in a separate network-enabled container and supply its token at runtime. Record that execution as remote simulation. Flashing or verifying a physical device is a separate bench action.
