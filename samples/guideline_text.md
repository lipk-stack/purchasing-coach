# XXEON IT Procurement Guideline

Version 1.0 | Confidential | Internal Use Only

## 3 INTRODUCTION

### 3.1 Purpose of the Document

This document serves as the primary reference for all IT teams within XXEON when undertaking any form of IT procurement activity. It provides a structured and consistent framework to ensure alignment with XXEON's internal policies, uniformity in vendor engagements, and the safeguarding of the organisation's interests. All IT purchases must be guided by the principles set out in this document. Adherence to these guidelines supports streamlined procurement processes, strengthens vendor oversight, and mitigates risks associated with non-compliance. This document is reviewed and updated periodically to reflect current industry standards, regulatory changes, and internal governance requirements. Its broad coverage across diverse IT procurement scenarios enables teams to apply the relevant sections based on their specific operational needs.

### 3.2 Scope and Applicability

These guidelines apply to all IT-related procurement activities, encompassing but not limited to hardware, software, cloud services, professional consulting, and IT infrastructure solutions. All IT teams, irrespective of department or geographic location, are required to adhere to these guidelines throughout any vendor engagement or procurement process.

This document is strictly for internal XXEON use and SHALL NOT be shared with vendors, prospective vendors, or any external parties.

## 4 CONTRACT REQUIREMENTS

### 4.1 Standard Contract Terms and Conditions

The vendor shall be responsible for all stamp duty costs associated with any required agreements.

All services and products to be delivered must be precisely defined within the contract.

Pricing structures and detailed payment terms must be explicitly stated to ensure mutual clarity.

Delivery schedules and project milestones must be specified to effectively manage expectations.

Acceptance criteria and quality assurance procedures must be clearly established prior to delivery.

Confidentiality and non-disclosure obligations (NDAs) are mandatory wherever sensitive information is involved; a one-way NDA is the recommended approach.

Contracts must incorporate limitation of liability provisions and clearly defined dispute resolution mechanisms for any conflicts arising during the contractual period.

### 4.2 Service Level Agreements (SLAs)

SLAs must be thorough, defining key performance indicators (KPIs), minimum service thresholds, and the consequences of non-compliance.

SLAs must incorporate provisions for scheduled performance reviews facilitated by XXEON's IT Vendor Management Office, with documented coverage of response times, service availability, performance benchmarks, and issue resolution.

Financial penalties for SLA breaches or violations of incident and change management protocols must be explicitly defined.

### 4.3 Pricing and Payment Terms

All costs — both one-time and recurring — must be transparently itemised.

A detailed payment schedule aligned to project milestones, monthly, quarterly, or annual cycles must be defined.

Provisions for any prospective price adjustments must be included to ensure predictability and transparency.

Acceptable payment methods and currencies, including foreign exchange considerations for long-term contracts, must be specified.

Vendors are required to submit a comprehensive Bill of Materials (BOM) covering all hardware, software, licences, accessories, and ancillary equipment. Refer to the Appendix for the SBOM declaration template.

Vendors assume full responsibility for any component shortfalls and must supply such shortfalls at no additional cost to XXEON.

All costs associated with integrating the proposed solution into XXEON's existing IT environment must be included in the vendor's quotation to prevent unforeseen expenditure.

### 4.4 Contract Duration and Renewal Options

The initial contract term must be clearly defined, including its duration and relevant conditions.

Comprehensive provisions for contract extensions and renewals must be included to facilitate smooth transitions.

A structured renegotiation process at renewal must be outlined to maintain equitable terms for both parties.

### 4.5 Termination Clauses

Clear and mutually understood conditions under which either party may terminate the agreement must be defined.

Required notice periods must be specified, including provisions for data extraction or data preservation, particularly for cloud-hosted solutions.

Post-termination obligations and entitlements of both parties, including deliverables and handover responsibilities, must be explicitly documented.

Transition assistance provisions to ensure a smooth handover of duties and institutional knowledge must be included.

### 4.6 Intellectual Property Rights

Ownership rights over any intellectual property created throughout the engagement must be clearly defined.

Licensing terms for the use of the vendor's proprietary technologies must be explicitly stated.

Adequate protections for XXEON's intellectual property must be stipulated in all contracts.

Vendors must warrant that their products and services do not infringe upon any third-party intellectual property rights.

Vendors shall bear full liability for any consequences arising from infringement of third-party intellectual property rights.

For all IT solutions developed for and owned by XXEON, vendors must ensure that all brand elements — including typography — comply with XXEON's corporate Brand Guidelines. Written acceptance of liability for any copyright violations related to brand elements is required where full compliance cannot be guaranteed. Any deviations must use legally licensed elements documented in the SBOM.

### 4.7 Rights and Compensation

Contracts must include a clause confirming that XXEON and its group of companies do not waive their rights of recourse against the service provider.

Indemnification clauses protecting XXEON from financial losses resulting from the service provider's actions or negligence must be included.

Service providers must maintain valid professional indemnity (PI) or errors and omissions (E&O) insurance, with minimum coverage amounts specified and the policy maintained throughout the contract term — particularly for outsourcing arrangements.

## 5 INFORMATION SECURITY CONSIDERATIONS

### 5.1 Data Protection and Privacy Compliance

Vendors must demonstrate compliance with applicable data protection legislation, including the Personal Data Protection Act (PDPA) and Payment Card Industry Data Security Standard (PCI DSS).

Vendors must maintain current and comprehensive privacy policies addressing data handling, storage, and deletion procedures.

Regular compliance audits and certifications are mandatory to verify continued adherence to applicable regulations.

### 5.2 Information Security Standards

Vendors must operate in accordance with all applicable legal, privacy, and data retention requirements and must disclose the compliance standards they observe.

Compliance with XXEON IT's information security policies and standards is mandatory without exception.

Minimum security baselines must be specified, including adherence to ISO 27001 or equivalent security control frameworks.

Periodic security assessments and penetration tests are required to ensure continued compliance.

Vendors must maintain a documented Information Security Management System (ISMS) to systematically protect sensitive information.

### 5.3 Access Control and Authentication Requirements

Multi-factor authentication (MFA) must be enforced for all user accounts.

Role-based access control (RBAC) must be implemented to align permissions with user responsibilities.

Access permissions and user accounts must be subject to regular reviews and audits.

Password policies must enforce a minimum of 8 characters, complexity requirements, account lockout after three failed login attempts, mandatory periodic changes, and password history to prevent reuse. Refer to XXEON's Password Policy for the current requirements.

Integration with XXEON Single Sign-On (SSO) is required where applicable.

Direct access by support personnel to production environments must be restricted to operationally necessary instances only.

Production systems must be protected against unauthorised modification, insertion, or deletion by users.

A complete inventory of all default and service accounts must be provided, with unused or local accounts removed or disabled.

### 5.4 Encryption

Minimum encryption standards for data at rest and in transit must be defined, with vendors specifying the encryption standards employed in accordance with industry best practice.

Robust key management procedures must be established and enforced to protect encryption keys.

All confidential, critical, and sensitive data — whether stored or transmitted — must be encrypted using industry-recognised standards.

All administrative network functions must be encrypted to preserve data integrity and prevent unauthorised access.

### 5.5 Incident Response and Breach Notification Procedures

Vendor responsibilities in the event of a security incident or data breach must be clearly defined.

Maximum breach notification timeframes must be explicitly established.

Vendors must develop, maintain, and regularly test a comprehensive incident response plan.

Communication protocols to be followed during security incidents must be explicitly defined.

### 5.6 Audits and Assessments

Annual third-party security audits are mandatory to maintain comprehensive risk management and industry compliance.

Vendors must share detailed security assessment findings, including identified vulnerabilities and corresponding remediation plans.

Strict remediation timeframes for addressing vulnerabilities must be specified.

Right-to-audit clauses must be included in all vendor agreements.

Comprehensive audit trails tracking all access to network resources, user logins, queries, and activities must be implemented and maintained.

Audit logs must be in an analysable format and must record all administrative activities.

Audit logs must be protected against tampering, with all attempts to alter or delete logs logged and reported.

Cloud and SaaS providers must supply an annual SOC 2 Type II report to XXEON.

All third-party subscribed services must provide access to security logs via vendor-supported APIs or approved log-shipping methods, with SLAs covering log availability, delivery latency, retention periods, and applicable rate limits.

### 5.7 System Configuration

All default configurations must be reviewed and any settings that expose the system to risk must be modified prior to deployment.

Vendors must provide comprehensive server hardening checklists covering operating systems and databases for evaluation before implementation.

All environments containing production data must be subject to protective measures at least equivalent to those applied in production.

## 6 SOLUTION INTEROPERABILITY AND FLEXIBILITY

### 6.1 Compatibility with Existing Systems and Infrastructure

Vendors must provide detailed compatibility matrices identifying all required integrations and addressing potential issues during integration testing and implementation, including responsibility for remediation.

Both server and client components must be synchronised with XXEON's local time server. Web-based systems must support Microsoft Edge as a compatible browser.

Vendors must specify the solution architecture (client-server or web-based) and, for on-premises deployments, confirm compatibility with XXEON's virtualisation platform. Supported database platforms — including MS SQL, DB2, and MySQL — must be clearly identified.

### 6.2 Open Standards and APIs

Solutions must support open standards and protocols to maximise interoperability and flexibility.

Comprehensive API documentation, including full functionality descriptions and performance metrics, must be provided.

Data exchange formats must conform to recognised industry standards.

All interface channels to external platforms must be secured using measures such as HTTPS and encryption to protect data integrity and confidentiality.

### 6.3 Scalability and Future Expansion Capabilities

Vendors must provide detailed scalability metrics and benchmarks demonstrating the system's capacity to accommodate projected growth, including options for horizontal and vertical scaling.

A clear product roadmap with specific timelines and milestones for anticipated features and enhancements must be provided.

Minimum network bandwidth requirements for optimal operation must be specified to support infrastructure planning.

### 6.4 Customisation Options

Vendors must clearly outline available customisation levels, including user interfaces, workflows, and reporting features, along with the methodology, tools, and processes for implementing them.

All customisations must be fully documented for future reference and continuity.

Ownership and maintenance responsibilities for custom components must be explicitly defined.

### 6.5 Data Migration and Export Capabilities

Vendors must provide a comprehensive data migration plan detailing methodologies, supported import and export formats, and tools for data export, trial migration, and validation.

A backend data extraction utility must be provided, enabling export of data in CSV or other standardised formats as required by XXEON IT.

## 7 SUPPORT AND MAINTENANCE

### 7.1 Support Availability

Required support coverage hours (e.g., 24/7 or standard business hours) must be specified.

Multiple support channels — including phone, email, and live chat — must be made available.

Vendors must provide detailed escalation procedures with relevant contact information.

Language requirements for support services must be explicitly stated.

### 7.2 Response Time Commitments

Maximum response times for each severity level must be clearly defined.

Vendors must submit regular reports on support performance metrics.

Penalties or corrective actions for failure to meet response time commitments must be defined.

### 7.3 Escalation Procedures

A comprehensive escalation matrix with defined contacts, steps, and timeframes for each escalation level must be provided.

Both technical and managerial escalation paths must be documented, and vendors must furnish evidence of back-to-back support arrangements with their product principals.

### 7.4 Regular Maintenance Schedules

Annual maintenance calendars must be provided and maintenance windows aligned with XXEON's operational schedule to minimise disruption.

Advance notifications for all scheduled maintenance must be issued with adequate lead time.

Post-maintenance performance reports and validations must be submitted following each maintenance activity.

### 7.5 Update and Patch Management

Defined timelines for the deployment of security patches and updates must be stipulated.

Detailed release notes for all updates must be provided.

Comprehensive rollback procedures must be included for all updates.

A rigorous testing and approval process for major updates must be specified.

All hardware, software, firmware, and patches must be maintained at current supported versions.

### 7.6 Backup and Restore

Vendor solutions must integrate with XXEON's existing backup infrastructure, including platforms such as Commvault and Veritas NetBackup.

Automated scheduled backups that do not interrupt system operations must be implemented.

Proposed backup strategies — including local, full, and incremental options — must be documented and submitted.

All backup and restore procedures must be tested during the implementation phase.

Backups containing critical, sensitive, or confidential data must be encrypted and password-protected.

### 7.7 Knowledge Transfer and Documentation

Vendors must deliver comprehensive documentation, including user manuals, technical guides, system documentation, network diagrams, and troubleshooting references. All materials must be organised and stored in XXEON's SharePoint with appropriate access controls.

Regular knowledge transfer sessions for key XXEON personnel are required, supported by an up-to-date knowledge base or FAQ repository maintained by the vendor.

All documentation produced in connection with XXEON engagements remains the property of XXEON. Vendors must also contribute to mandatory project documentation as required by XXEON's Project Management Guideline, including the Project Charter, PMC, FAC, and JC where applicable.

### 7.8 Records and Assessment Requirements

Vendors must develop and maintain accurate and current records of service performance and contractual obligations, encompassing all relevant books, records, documents, and equipment inventories.

Copies of records must be made available to XXEON IT upon reasonable request, in hard copy or an agreed electronic format.

XXEON IT reserves the right to review or assess vendor records through its personnel, agents, auditors, advisors, or regulatory representatives.

## 8 HARDWARE REQUIREMENTS

### 8.1 Compatibility with XXEON Infrastructure

Vendors must supply detailed compatibility lists confirming full alignment with XXEON's existing infrastructure.

Support for XXEON's virtualisation platforms, where applicable, is required, including installation, configuration, and hardening of servers and associated components. Unnecessary protocols and services must be disabled and all active ports justified.

### 8.2 Performance Specifications

Minimum performance thresholds — including processing speed, memory, and storage — must be defined.

Benchmark results demonstrating compliance with specified criteria must be submitted.

Stress testing procedures and anticipated performance under peak load conditions must be documented.

### 8.3 Energy Efficiency Standards

Vendors must comply with specified energy efficiency certifications, such as ENERGY STAR.

Detailed power consumption metrics for all proposed hardware must be provided.

Power management features to optimise energy consumption must be incorporated.

### 8.4 Warranty and Replacement Policies

Minimum warranty periods for each hardware category must be specified.

Acceptable repair or replacement timeframes must be clearly defined.

Extended warranty options must be offered.

Clear procedures for warranty claims and returns must be documented.

End-of-Sale and End-of-Support dates for all proposed equipment must be declared.

### 8.5 Hardware Disposal and Recycling

Environmentally responsible hardware disposal options must be offered, in compliance with applicable e-waste regulations.

Secure data wiping procedures for all decommissioned hardware are mandatory to protect sensitive information.

### 8.6 Physical Security

Stringent physical access controls for all servers, storage units, USB devices, backups, and hard drives must be implemented and monitored.

Wireless, infrared, and unused input-output ports and network services must be deactivated.

## 9 SOFTWARE REQUIREMENTS

### 9.1 Licensing Models and Terms

Preferred licensing models — including perpetual, subscription-based, or per-user — must be specified in alignment with organisational requirements.

Comprehensive licensing terms and conditions, including all constraints and limitations, must be clearly documented.

License management tools or dashboards must be included to facilitate efficient tracking and compliance.

Transferability and reassignment rights of licences must be specified to support operational flexibility.

### 9.2 Software Update and Upgrade Policies

Expected frequency of software updates must be specified to ensure timely security and performance improvements.

Entitlement to major version upgrades within licensing terms must be clarified for strategic planning purposes.

Long-term support options for specific software versions must be available.

Advance notification of end-of-life or deprecated features is mandatory to allow adequate transition planning.

### 9.3 Compatibility with XXEON Systems and Platforms

Compatibility with XXEON's supported operating systems and versions must be confirmed.

A detailed browser compatibility matrix must be provided where applicable.

Mobile platform support must be mandated where business operations require it.

### 9.4 User Access and Account Management

User provisioning and deprovisioning requirements must be specified; where feasible, user access must be integrated with XXEON's Identity Management solution.

Single sign-on (SSO) and directory integration must be supported to streamline authentication and security.

Role-based access control must be included to enforce appropriate access levels.

Audit logging for user activities must be implemented for accountability and security monitoring.

Vendors must provide capabilities to track, trace, and report on user activities, including detection of account dormancy.

All privileged IDs within the solution — across operating systems, databases, applications, and utilities — must be integrated with XXEON's Privileged Access Management platform.

### 9.5 Application Monitoring

Vendors must clearly specify the types of logs and events generated by the application, including their exact storage locations.

Application logs must be retained for a minimum of three years to support long-term accountability and future audit requirements.

Robust measures to prevent log tampering or unauthorised access must be implemented to preserve data integrity.

### 9.6 Training and Onboarding Support

Comprehensive initial training programmes for both administrators and end-users are required to ensure proficiency from go-live.

Ongoing training requirements, including available formats such as online webinars and in-person sessions, must be specified.

Self-paced learning resources must be provided to accommodate varied learning styles.

Training environments or sandbox instances for hands-on practice must be available.

## 10 FINANCIAL CONSIDERATIONS

### 10.1 Total Cost of Ownership (TCO) Analysis

A comprehensive TCO analysis spanning a minimum of five years must be provided, encompassing all direct and indirect costs including licensing, hardware, maintenance, training, and upgrades.

All potential hidden costs or fees over the specified period must be disclosed to ensure full financial transparency.

A comparative TCO analysis against equivalent market solutions should be provided where feasible to support informed decision-making.

### 10.2 Return on Investment (ROI) Projections

Detailed ROI projections with supporting assumptions must be provided, specifying KPIs such as productivity gains, cost savings, and revenue impact.

Case studies or references demonstrating achieved ROI from comparable implementations must be included.

A sensitivity analysis illustrating ROI outcomes under varying conditions must be conducted to support risk-informed decision-making.

### 10.3 Budget Approval Process

Internal budget approval workflows, including required documentation such as a business case and cost-benefit analysis, must be clearly defined.

Approval thresholds for different levels of authority must be adhered to.

Periodic budget reviews for ongoing projects or subscriptions are required to ensure continued financial oversight.

### 10.4 Payment Schedules and Milestones

Preferred payment terms (monthly, quarterly, or annual) must be specified.

Payment schedules must align with project milestones or deliverables to link disbursements to tangible progress.

Holdback or retention percentages for project-based engagements must be defined.

Acceptable payment methods and currencies must be specified.

## 11 COMPLIANCE AND RISK MANAGEMENT

### 11.1 Regulatory Compliance

All relevant industry-specific regulations (e.g., HIPAA, SOX, PCI-DSS) must be identified and vendors required to provide compliance certifications, with regular audits mandated.

Vendors must comply with all applicable laws governing their activities and XXEON's operations, including mandatory adherence to PDPA and PCI DSS.

For engagements involving cybersecurity products or services, vendors must comply with the Malaysia Cybersecurity Act (Act 854), which mandates that all providers hold a valid licence.

Vendors offering IaaS or PaaS to XXEON must comply with MCMC requirements for an ASP (C) licence, providing a copy to XXEON upon award and at each renewal.

Vendors must process personal data in accordance with PDPA and/or PCI DSS and must notify XXEON of any enquiries or orders from data protection authorities relating to data obtained under the contract.

All electronic hardware components must meet regulatory standards and hold required SIRIM or MCMC certifications.

### 11.2 Vendor Risk Assessment

Vendors must complete a comprehensive risk assessment questionnaire to identify risks associated with their services and products.

Minimum acceptable risk ratings must be met, particularly for vendors providing critical services. Annual risk reassessments are required.

Full disclosure of all subcontractors and third-party hardware or software dependencies is mandatory.

A detailed Software Bill of Materials (SBOM) declaration must be provided (refer to the Appendix for the template) to enable thorough evaluation of component-level risks.

Software vendors and development service providers must provide written assurance of adherence to secure coding standards and practices.

### 11.3 Cybersecurity Assessment Concentration Risks

The same vendor shall not be engaged for consecutive annual cybersecurity assessments unless they are the sole qualified provider for the required service.

A single vendor must not conduct more than one type of cybersecurity assessment (e.g., penetration test, compromise assessment) in the same calendar year.

Cost must not be the sole selection criterion for cybersecurity assessments; evaluation criteria must include methodology robustness, relevant expertise, independence, licensing, and track record.

Any exceptions to the above must be documented with detailed justification and approved explicitly by the XXEON Governance team.

### 11.4 Business Continuity and Disaster Recovery Plans

Vendors must provide comprehensive business continuity and disaster recovery plans specifying maximum acceptable RTO and RPO values, with procedures subject to regular testing.

Post-incident reports detailing service disruptions, root causes, and preventive measures must be submitted. RPO in the event of a disaster at the primary hosting location must be clearly stated.

RTO for recovery at the secondary hosting location must be specified, and any capability for endpoint clients to continue operating without server connectivity must be disclosed.

Alternative provisions for business continuity during system downtime and guaranteed system uptime must be documented.

### 11.5 Insurance Requirements

Vendors must maintain adequate insurance coverage, including specified minimum amounts for general liability and cyber risks.

Certificates of insurance must be provided as proof of coverage, with any changes in coverage promptly communicated.

Where applicable, XXEON must be named as an additional insured party.

## 12 POST-IMPLEMENTATION

### 12.1 Performance Evaluation Criteria

Clear KPIs for assessing solution effectiveness must be established, with vendors required to provide regular and transparent performance reports.

Post-implementation reviews must be conducted at 3, 6, and 12-month intervals to evaluate progress and identify improvement opportunities.

Standardised procedures for addressing performance shortfalls must be implemented and enforced.

### 12.2 User Feedback Collection

Methods for gathering user feedback — such as structured surveys and focus groups — must be specified.

Vendors must implement continuous feedback mechanisms to foster transparency and responsiveness.

Regular reviews and analyses of user feedback are mandatory for trend identification and service improvement.

Defined processes for incorporating user feedback into solution enhancements must be established.

### 12.3 Continuous Improvement Process

Vendors must provide a comprehensive solution or service roadmap with regular feature enhancements and optimisation activities.

Periodic reassessments of the solution's relevance against evolving user needs and available market alternatives are required.

Structured procedures for suggesting and implementing improvements must be defined to ensure systematic integration of enhancements.

## 13 APPENDIX

### 13.1 Software Bill of Materials (SBOM) Template

Vendors are required to complete and submit the SBOM template below for all software components proposed as part of their solution. The SBOM must enumerate all software libraries, frameworks, dependencies, and third-party components included in the delivered product. Each entry must specify the component name, version, licence type, source, and any known vulnerabilities. This declaration supports XXEON's risk management obligations and ensures transparency in the composition of vendor-supplied solutions.

The completed SBOM must be submitted as part of the vendor's proposal and updated as required throughout the contract lifecycle to reflect any changes to the software composition.
