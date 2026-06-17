"""Decision-tree scenario data for the Template backend.

Each scenario defines:

- **keywords** used to auto-detect the procurement category from free text,
- **questions** presented to the buyer during the interview phase,
- **always_sections** — guideline section roots that apply unconditionally,
- **conditional_sections** — section roots included only when the buyer's
  answers satisfy the listed boolean expressions, and
- **guidance** — pre-authored advisory text surfaced during chat.

Section numbers follow the XXEON IT Procurement Guideline:

    4  Contract Management
    5  Information Security
    6  Integration
    7  Support / Maintenance
    8  Hardware
    9  Software
    10 Financial
    11 Compliance & Risk
    12 Post-Implementation
"""

SCENARIOS: dict[str, dict] = {
    "hardware": {
        "name": "Hardware Procurement",
        "keywords": [
            "hardware", "server", "laptop", "desktop", "device", "appliance",
            "network", "switch", "router", "storage", "physical", "equipment",
        ],
        "questions": [
            {
                "key": "hw_type",
                "question": "What type of hardware are you procuring?",
                "options": [
                    "Servers/Compute",
                    "Networking Equipment",
                    "End-user Devices",
                    "Storage Systems",
                    "Other",
                ],
            },
            {
                "key": "hw_scale",
                "question": "What is the deployment scale?",
                "options": [
                    "Small (<50 units)",
                    "Medium (50-500 units)",
                    "Large (500+ units)",
                ],
            },
            {
                "key": "hw_criticality",
                "question": "What is the business criticality level?",
                "options": ["Mission-critical", "Important", "Standard"],
            },
            {
                "key": "hw_data",
                "question": (
                    "Will the hardware store or process sensitive/personal "
                    "data?"
                ),
                "options": [
                    "Yes - personal/sensitive data",
                    "Yes - internal data only",
                    "No sensitive data",
                ],
            },
            {
                "key": "hw_network",
                "question": "Will the hardware connect to the internal network?",
                "options": [
                    "Yes - internal network",
                    "Yes - internet-facing",
                    "Standalone",
                ],
            },
        ],
        # Sections that always apply to hardware procurement.
        "always_sections": ["4", "5", "11"],
        # Conditional section inclusion keyed on buyer answers.
        "conditional_sections": {
            "hw_network != Standalone": ["5", "6"],
            "hw_scale == Large (500+ units) OR hw_criticality == Mission-critical": ["7"],
            "hw_scale == Large (500+ units)": ["10"],
            # Hardware (8) and post-implementation (12) always apply to a
            # hardware buy. Kept as one "true" entry — a dict literal silently
            # drops a repeated key, which previously lost section 8 entirely.
            "true": ["8", "12"],
        },
        "guidance": {
            "general": (
                "Hardware procurement requires careful consideration of "
                "warranty terms, deployment logistics, and ongoing support "
                "agreements. Refer to Section 8 of the guideline for "
                "hardware-specific requirements."
            ),
            "security": (
                "All hardware connecting to the corporate network must comply "
                "with the information security requirements in Section 5, "
                "including firmware update policies and secure boot "
                "capabilities."
            ),
            "contract": (
                "Hardware contracts should include provisions for warranty, "
                "spare parts availability, and end-of-life/end-of-support "
                "timelines per Section 4."
            ),
        },
    },
    "software": {
        "name": "Software & Licensing",
        "keywords": [
            "software", "license", "application", "subscription", "saas",
            "cloud", "platform", "tool", "system",
        ],
        "questions": [
            {
                "key": "sw_type",
                "question": "What type of software are you procuring?",
                "options": [
                    "On-premise Software",
                    "Cloud/SaaS",
                    "Development Tools",
                    "Business Applications",
                    "Other",
                ],
            },
            {
                "key": "sw_license",
                "question": "What licensing model is preferred?",
                "options": [
                    "Perpetual License",
                    "Subscription",
                    "SaaS/Cloud",
                    "Open Source",
                    "Freemium/Usage-based",
                ],
            },
            {
                "key": "sw_data",
                "question": "Will the software handle personal or payment data?",
                "options": [
                    "Yes - personal data (PDPA)",
                    "Yes - payment data (PCI DSS)",
                    "Yes - both",
                    "No sensitive data",
                ],
            },
            {
                "key": "sw_integration",
                "question": "Does it need to integrate with existing systems?",
                "options": [
                    "Yes - SSO/IAM",
                    "Yes - databases/APIs",
                    "Yes - both",
                    "Standalone",
                ],
            },
            {
                "key": "sw_users",
                "question": "How many users will access the software?",
                "options": [
                    "Small team (<25)",
                    "Department (25-200)",
                    "Enterprise (200+)",
                ],
            },
        ],
        "always_sections": ["4", "5", "11"],
        "conditional_sections": {
            "sw_integration != Standalone": ["6"],
            "sw_type == Cloud/SaaS OR sw_license == SaaS/Cloud": ["11"],
            "sw_license == Perpetual License OR sw_license == Subscription": ["9"],
            "sw_users == Enterprise (200+)": ["10"],
            # Support (7) and post-implementation (12) always apply to a
            # software buy. Merged into one "true" entry — a repeated dict key
            # previously dropped section 7.
            "true": ["7", "12"],
        },
        "guidance": {
            "general": (
                "Software procurement involves licensing terms, data handling "
                "obligations, and integration requirements. Section 9 covers "
                "software-specific provisions."
            ),
            "security": (
                "Software handling personal data must comply with PDPA "
                "requirements in Section 5. Payment data requires PCI DSS "
                "compliance verification."
            ),
            "contract": (
                "Review license terms carefully for termination, renewal, and "
                "data portability clauses per Section 4."
            ),
        },
    },
    "services": {
        "name": "Professional Services",
        "keywords": [
            "service", "consulting", "consultant", "managed", "outsourcing",
            "staff", "professional", "engagement", "contractor",
        ],
        "questions": [
            {
                "key": "svc_type",
                "question": "What type of services are you procuring?",
                "options": [
                    "IT Consulting",
                    "Managed Services",
                    "Staff Augmentation",
                    "Implementation/Integration",
                    "Training",
                ],
            },
            {
                "key": "svc_duration",
                "question": "What is the expected engagement duration?",
                "options": [
                    "Short-term (<3 months)",
                    "Medium (3-12 months)",
                    "Long-term (12+ months)",
                ],
            },
            {
                "key": "svc_access",
                "question": "Will the service provider access internal systems?",
                "options": [
                    "Yes - full access",
                    "Yes - limited access",
                    "No system access needed",
                ],
            },
            {
                "key": "svc_deliverables",
                "question": "Are there specific deliverables or milestones?",
                "options": [
                    "Yes - defined deliverables",
                    "Yes - milestones only",
                    "Time & materials",
                ],
            },
            {
                "key": "svc_data",
                "question": "Will the provider handle sensitive data?",
                "options": [
                    "Yes - personal data",
                    "Yes - confidential business data",
                    "No sensitive data",
                ],
            },
        ],
        "always_sections": ["4", "11"],
        "conditional_sections": {
            "svc_access != No system access needed": ["5", "6"],
            "svc_type == Managed Services": ["7"],
            "svc_duration == Long-term (12+ months)": ["10"],
            "true": ["12"],
        },
        "guidance": {
            "general": (
                "Professional services procurement requires clear scope "
                "definition, deliverable acceptance criteria, and IP ownership "
                "terms."
            ),
            "security": (
                "Service providers accessing internal systems must undergo "
                "security assessment per Section 5 and sign appropriate NDAs."
            ),
            "contract": (
                "Service contracts should include performance benchmarks, "
                "termination for convenience, and knowledge transfer "
                "provisions per Section 4."
            ),
        },
    },
    "cybersecurity": {
        "name": "Cybersecurity Services",
        "keywords": [
            "cybersecurity", "cyber security", "penetration test", "pen test",
            "vulnerability", "audit", "compliance", "security assessment",
            "soc", "iso",
        ],
        "questions": [
            {
                "key": "cy_type",
                "question": "What type of cybersecurity service?",
                "options": [
                    "Penetration Testing",
                    "Security Audit/Assessment",
                    "Compliance Certification",
                    "Managed Security (SOC)",
                    "Security Consulting",
                ],
            },
            {
                "key": "cy_scope",
                "question": "What is the scope of the assessment?",
                "options": [
                    "Specific application/system",
                    "Network infrastructure",
                    "Organization-wide",
                    "Cloud environment",
                ],
            },
            {
                "key": "cy_classification",
                "question": "What is the data classification level?",
                "options": [
                    "Highly Confidential",
                    "Confidential",
                    "Internal",
                    "Public",
                ],
            },
            {
                "key": "cy_standard",
                "question": "Are there specific compliance standards required?",
                "options": [
                    "ISO 27001",
                    "SOC 2 Type II",
                    "PCI DSS",
                    "Multiple standards",
                ],
            },
            {
                "key": "cy_frequency",
                "question": "What is the assessment frequency?",
                "options": [
                    "One-time",
                    "Annual",
                    "Quarterly",
                    "Continuous monitoring",
                ],
            },
        ],
        "always_sections": ["4", "5", "11"],
        "conditional_sections": {
            "cy_type == Managed Security (SOC)": ["7"],
            "cy_frequency == Continuous monitoring OR cy_frequency == Quarterly": ["10"],
            "true": ["12"],
        },
        "guidance": {
            "general": (
                "Cybersecurity services require special attention to assessor "
                "qualifications, scope definition, and handling of "
                "findings/reports."
            ),
            "security": (
                "Assessors must hold relevant certifications and the "
                "engagement must follow Section 5 requirements for security "
                "assessments."
            ),
            "contract": (
                "Include confidentiality provisions, findings handling "
                "procedures, and re-assessment timelines per Section 4."
            ),
        },
    },
}

# Quick lookup: keyword -> scenario name.  Built once at import time so
# ``detect_scenario`` is a single dict lookup per keyword.
KEYWORD_INDEX: dict[str, str] = {}
for _name, _scenario in SCENARIOS.items():
    for _kw in _scenario["keywords"]:
        KEYWORD_INDEX[_kw] = _name
