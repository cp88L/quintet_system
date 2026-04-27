## Cluster step: missing-data behaviour

When a product has no bar for a given day, it is silently absent from that day's cluster cross-section and no `prob` is computed for it. The backtest's state machine does the same — it iterates only available rows, skipping the gap day, and enters trades normally on the first available bar afterwards. The product returns to full cluster participation as soon as its next bar arrives.

## Notes

`SNLME` is the IBKR `LMEOTC` Tin lookalike. We are missing bars on some zero-volume days in the lookalike even though the underlying LME Tin market may still have volume.
