# Sample agent messages for Track C

Task for C: for scenarios S2, S3 and S4, write the full message sequence in this shape so F can build the transcript panel.
Post each with `POST /cases/{id}/messages`. The first is a worked example (a water leak first sent to the wrong department).

```json
[
  {
    "from_agent": "corporation",
    "type": "reject",
    "target_department": "water_board",
    "reason": "Asset is a water main, not a road surface defect",
    "evidence": [{"kind": "registry", "ref": "corp-registry/asset/none", "summary": "No road asset at coordinates"}]
  },
  {
    "from_agent": "water_board",
    "type": "accept",
    "reason": "Pipe PW-4471 is on our network at this location",
    "evidence": [{"kind": "registry", "ref": "water-registry/pipe/PW-4471"}]
  }
]
```

Fields: `from_agent` and `target_department` are one of `corporation | water_board | electricity | highways`.
`type` is `accept | reject | transfer | request_info | escalate`. `evidence[].kind` is `registry | photo | boundary | history | note`.
`reject` and `transfer` are invalid without a target and evidence.

- S2: TODO (C)
- S3: TODO (C)
- S4: TODO (C)
