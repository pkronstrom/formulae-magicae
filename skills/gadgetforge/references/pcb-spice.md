# Optional PCB simulation check

Use ngspice when the PCB work raises a specific circuit question that a model can answer. Start in KiCad's schematic simulator for interactive exploration. For a repeatable check, prepare a small SPICE netlist or export the needed KiCad schematic. Check the model pin mapping. Supply the actual device models, loads, and stimuli needed for the claim. [KiCad simulation](https://www.kicad.org/discover/spice/), [KiCad netlist export](https://docs.kicad.org/10.0/en/cli/cli.html#_schematic_export_netlist)

Good candidates are regulator startup or load-step droop, RC timing, bias points, and audio filter response. Choose the measurement, units, acceptance bounds and operating conditions before running it. After routing, repeat a targeted check if the layout adds a consequential effect. Represent that effect with an estimated or extracted parameter and say where it came from. A schematic netlist does not include the routing geometry by default. Retain the normal board checks. Report circuit coverage separately from physical validation.

## Run the plugin

The standalone runner uses the `ngspice` executable on `PATH`. It needs no Gadgetforge state and never advances a phase. Use a reviewed netlist, define named `.measure` results, and include the corresponding `.print` or `.plot` command for batch mode. One run should produce each requested measurement exactly once. Run separate cases for operating or tolerance extremes that matter. [ngspice manual, measurements and batch output](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf#page=342)

For example, a small RC fixture can check settling after a step. Save this as `filter.cir`:

```spice
RC settling example
Vstep in 0 PULSE(0 3.3 0 1u 1u 10m 20m)
Rfilter in out 10k
Cfilter out 0 100n
.tran 50u 5m
.measure tran vout_final FIND v(out) AT=4m
.print tran v(out)
.end
```

```sh
python3 <skill-dir>/scripts/pcb_spice.py filter.cir \
  --expect vout_final 3.20 3.30 --report filter-check.json
```

The report records the result, invocation, input hash, measurement values and bounds, and simulator log. `--expect` can be repeated. `pass` means every requested value was present and inside its inclusive limits. `fail` means an available value exceeded its limits. `unknown` covers incomplete measurements or simulator errors. Exit codes are 0, 1 and 2 respectively. For a failed invocation, check the exit code and new report before relying on any old report at that path.

Save the reviewed netlist, model file identities, operating conditions, simulator version, report and any useful plot in the project. Register the netlist and local model files with `capture --uses` when the check informs phase acceptance. Where appropriate, attach the JSON to the existing `electrical` or `layout` evidence using `evidence --report`. Record what the simulation actually checked. The plugin report covers the named metrics. The phase check also needs the other applicable electrical or layout evidence. Missing models or unresolved layout effects remain open when they matter to acceptance.
