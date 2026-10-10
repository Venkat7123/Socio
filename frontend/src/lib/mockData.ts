export const mockCases = [
  {
    case_id: "C-2026-000123",
    created_at: "2026-10-10T09:15:00Z",
    channel: "telegram",
    citizen: { id: "anon-481", language: "ta" },
    report: {
      text: "water standing on the road near the school",
      photos: ["https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?w=400"],
    },
    category: "waterlogging",
    severity: "high",
    location: { lat: 13.0000, lng: 80.0000, ward: "W-12", address_hint: "near school" },
    state: "DISPUTE",
    sla: { deadline: new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString(), breached: false },
    owners: [],
    hop_count: 1,
    rejected_by: ["water_board"],
    duplicate_of: null,
    messages: [
      {
        id: "m1",
        from: "water_board_agent",
        to: "engine",
        type: "reject",
        target: "corporation_agent",
        evidence: [
          { source: "water_board_registry", finding: "No pipeline asset within 50 m of the reported point", ref: "q-8841" }
        ],
        confidence: 0.82,
        timestamp: "2026-10-10T09:20:00Z",
        hop: 1
      },
      {
        id: "m2",
        from: "corporation_agent",
        to: "engine",
        type: "split",
        target: null,
        evidence: [
          { source: "drain_registry", finding: "Storm drain blocked at location", ref: "q-8842" },
          { source: "highways_registry", finding: "Road surface damaged", ref: "q-8843" }
        ],
        sub_tasks: [
          { department: "corporation", task: "Clear drain", rationale: "Drain blockage causing waterlogging" },
          { department: "highways", task: "Repair road", rationale: "Surface damage requires patching" }
        ],
        confidence: 0.95,
        timestamp: "2026-10-10T09:25:00Z",
        hop: 2
      }
    ]
  },
  {
    case_id: "C-2026-000124",
    created_at: "2026-10-10T08:00:00Z",
    channel: "app",
    citizen: { id: "anon-992", language: "en" },
    report: {
      text: "Massive pothole on main road",
      photos: ["https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?w=400"],
    },
    category: "pothole",
    severity: "medium",
    location: { lat: 13.0010, lng: 80.0020, ward: "W-12", address_hint: "Main junction" },
    state: "ASSIGNED",
    sla: { deadline: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), breached: true },
    owners: [{ sub_task_id: "T1", department: "corporation", task: "Patch pothole", status: "ASSIGNED" }],
    hop_count: 0,
    rejected_by: [],
    duplicate_of: null,
    messages: []
  },
  {
    case_id: "C-2026-000125",
    created_at: "2026-10-09T14:00:00Z",
    channel: "voice",
    citizen: { id: "anon-102", language: "hi" },
    report: {
      text: "Streetlight is out completely dark",
      photos: [],
    },
    category: "streetlight",
    severity: "medium",
    location: { lat: 13.0050, lng: 80.0050, ward: "W-14", address_hint: "Park avenue" },
    state: "ESCALATED",
    sla: { deadline: new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString(), breached: false },
    owners: [],
    hop_count: 2,
    rejected_by: ["corporation", "electricity"],
    duplicate_of: null,
    messages: [
      {
        id: "m3",
        from: "corporation_agent",
        to: "engine",
        type: "reject",
        target: "electricity_agent",
        evidence: [
          { source: "corp_assets", finding: "Pole #4422 belongs to Electricity Board", ref: "q-112" }
        ],
        confidence: 0.99,
        timestamp: "2026-10-09T14:10:00Z",
        hop: 1
      },
      {
        id: "m4",
        from: "electricity_agent",
        to: "engine",
        type: "reject",
        target: "corporation_agent",
        evidence: [
          { source: "elec_assets", finding: "Bulb replacement is municipal responsibility", ref: "q-113" }
        ],
        confidence: 0.90,
        timestamp: "2026-10-09T14:20:00Z",
        hop: 2
      }
    ]
  }
];
