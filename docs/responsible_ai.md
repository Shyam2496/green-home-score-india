# Responsible AI note

## Scope and reliability

This is a Hyderabad residential pilot with exploratory configurations for seven other cities. Training household labels are synthetic, so strong held-out accuracy measures the simulator's rules and noise. Sourced NASA/PVGIS references do not turn simulated household labels into measurements. The separate eleven-home RESIDE-AC audit uses anonymous real annual bills, but missing features prevent full observed-feature validation or national accuracy claims. Retrofit effects, costs and tariffs need independent validation before customer use.

The physical baseline omits humidity/latent cooling and space heating. This is particularly material in warm-humid cities and cold seasons outside Hyderabad. One weather year is not a climate normal. Capacity-limited AC profiles expose unmet thermal load; constant comfort cannot be assumed for those cases. Prospective deployment needs measured household inputs and outcomes, seasonal/geographic testing and independent surveys.

The Green Home Score is a transparent prototype score with the brief's weights, adapted to cooling, appliances and Indian home features. It is not an official building certification or survey. Energy, bill and carbon results are estimates. Financial cash flows depend on entered quotes, service assumptions and future tariffs. Property-value impact is deferred because verified local transactions linked to known retrofit histories and comparable-property controls are missing; valuation and hypothetical premium controls are omitted from the dashboard. Neither the score nor financial NPV establishes certification eligibility or resale appreciation. This is a documented scope gap, not a completed valuation feature.

## Privacy

Use fictional or non-identifying household features. Do not enter customer names, addresses, meter identifiers or confidential records. A downloaded report may contain every input supplied by the user. If optional LLM mode is enabled, the configured provider receives computed scenario facts; review the configured provider's data policy before using sensitive data. No API key is required for the default explanation mode.

## Bias and coverage

Synthetic sampling cannot represent the diversity of Indian housing, climate, occupancy, electricity access and household income. Climate and property type are coarse categories. Users outside the supported categories, or with unusual buildings and appliances, may receive unreliable estimates. Validate real-world errors by climate, size, property type, appliance efficiency and cooking fuel before deployment; report sample counts alongside each slice.

Ranking by purchased-energy reduction can favor high-consumption homes. It does not directly rank affordability, comfort, health or household need. Recommendations require a qualified survey and consent, including applicable society, ownership, roof, heritage and installation checks.

## Grounded explanations

Numeric facts originate in saved model outputs and explicit calculations. The default explanation is deterministic. Optional LLM explanations must select or explain existing facts without inventing estimates; failure or invalid output must fall back safely. Evaluate generated explanations separately from regression accuracy. The brief's targets (at least 90% groundedness and factual accuracy; less than 5% unsupported claims) are targets, not achieved results unless supported by a recorded evaluation.

## Human oversight and missing data

Unknown feasibility constraints are handled conservatively. A user should resolve missing or conflicting inputs before acting. Missing advanced engineering features may use disclosed assumptions; these values must not be presented as observations. Zero or missing baseline energy makes percentage improvement unavailable. Negative fuel savings remain visible when an intervention raises electricity, LPG or PNG use. A professional must review installation suitability and any financial or property decision.
