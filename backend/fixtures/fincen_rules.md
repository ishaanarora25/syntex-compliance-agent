# FinCEN Rules Digest

This digest is the authoritative quick-reference for the BSA/AML agent. Cite a section
inline as `[fincen:TAG]` (e.g. `[fincen:31CFR1010.230]`); the citation parser will resolve
the tag to a numbered footnote.

---

## [31CFR1010.230] Customer Due Diligence (CDD) Rule — 31 CFR § 1010.230

**Beneficial-ownership identification requirement.** Covered financial institutions must
identify and verify the identity of each beneficial owner of a legal entity customer at
account opening.

**Two prongs (both must be satisfied):**

- **Ownership prong:** Each individual who, directly or indirectly, owns **25% or more**
  of the equity interests of the legal entity customer.
- **Control prong:** **One** individual with significant managerial responsibility (CEO,
  CFO, COO, Managing Member, General Partner, President, Treasurer, or any other
  individual who regularly performs similar functions). The control-prong UBO is required
  even if no individual meets the 25% ownership threshold.

**Exempt legal entity customers** (no UBO collection required) include: SEC-registered
issuers, registered investment companies and advisers, banks, BHCs, credit unions, S&L
holding companies, FCM/IBs, public accounting firms, state-regulated insurance companies,
financial market utilities, and entities >50% owned by an exempt entity.

**Trust look-through:**
- **Statutory / business / commercial trusts** are treated as legal-entity customers.
- **Personal trusts** (most common in private banking): UBO = the **trustee** under the
  control prong; named beneficiaries with vested interests are also treated as beneficial
  owners for ownership purposes when their interest crosses 25%.
- **Revocable trusts:** the grantor retains beneficial ownership and is the UBO.
- **Irrevocable trusts:** trustee for control; named beneficiaries for economic interest;
  discretionary beneficiaries are not automatically UBOs absent a fixed interest.

**Verification:** identifying information for each UBO must be verified to a reasonable
risk-based standard (parallel to CIP). Documentary or non-documentary methods are
permitted.

---

## [31CFR1020.220] Customer Identification Program (CIP) — 31 CFR § 1020.220

**Required elements** for each customer (and each ≥25% UBO):

- Name
- Date of birth (for individuals)
- Residential or business address
- Identification number (SSN/ITIN for U.S. persons; passport / alien-ID number plus
  country of issuance for non-U.S. persons)

**Verification within a reasonable time after account opening** using documents
(unexpired government-issued ID showing nationality/residence) or non-documentary methods
(database checks, references, prior account history). For non-U.S. persons, government-
issued photo ID is the dominant practice.

**A blocking requirement.** Until CIP is satisfied for every UBO ≥25%, the case cannot
be cleared for ongoing relationship.

---

## [31USC5336] Corporate Transparency Act / BOI Reporting — 31 USC § 5336

**Effective Jan 1, 2024.** Reporting companies (corporations, LLCs, and similar entities
formed by filing with a Secretary of State) must report **Beneficial Ownership
Information** to FinCEN.

**Reporting beneficial owner** = any individual who:
- Exercises **substantial control** over the reporting company, OR
- Owns or controls **≥25%** of its ownership interests.

**Substantial control** examples: senior officer, authority to appoint/remove senior
officers or a majority of the board, directs important decisions, any other form of
substantial control.

**23 enumerated exemptions** include: large operating companies (>20 full-time U.S.
employees, >$5M U.S. gross receipts, physical U.S. office), most CDD-rule-exempt
entities, subsidiaries of exempt entities, inactive entities meeting criteria, etc.

**Filings:** initial report on formation; updated within 30 days of any change to
reported information. Failure to report carries civil and criminal penalties.

**Note for BSA review:** BOI is FinCEN-held and is *not* automatically available to the
financial institution. Treat the FI's CDD-collected UBO data as primary; flag any
ownership claims that would conflict with a likely BOI filing for follow-up.

---

## [trust-lookthrough] Trust Look-Through Conventions

The agent applies these (consistent with FinCEN CDD guidance and FFIEC BSA/AML Manual):

- **Revocable trust** → 100% pass-through to grantor (or weighted between joint grantors
  by `grantor_pcts`). Grantor is treated as both control and economic UBO.
- **Irrevocable trust:**
  - **Trustee** is a UBO under the control prong (regardless of percentage) and is
    flagged `ubo_by_control = true`.
  - **Named non-discretionary beneficiaries** receive economic-interest pass-through
    weighted by `beneficiary_pcts`. If any single beneficiary's pass-through ownership
    crosses 25%, they are also a UBO under the ownership prong.
  - **Purely discretionary beneficiaries** (no fixed interest) are not automatic UBOs;
    document-and-monitor.
- **Joint trust** (two grantors): default 50/50 between grantors unless `grantor_pcts`
  specifies otherwise.

These rules are implemented deterministically in `services/trust_logic.py`; the agent
should cite this section when the memo explains *why* a particular trust resolved the
way it did.

---

## [jurisdiction-risk] Jurisdiction Risk Reference

These lists are mirrored in `services/case_analyzer.py` and used to flag entities at
intake. Cite this section when explaining why a foreign-jurisdiction risk flag was
raised.

**FATF Black-list (Call for Action) — automatic high risk:**
- North Korea (DPRK)
- Iran
- Myanmar (Burma)

**FATF Grey-list (Increased Monitoring) — heightened due diligence; non-exhaustive
snapshot, refresh quarterly from FATF plenary:**
- Bulgaria, Burkina Faso, Cameroon, Croatia, DRC, Haiti, Kenya, Mali, Mozambique,
  Namibia, Nigeria, Philippines, Senegal, South Africa, South Sudan, Syria, Tanzania,
  Venezuela, Vietnam, Yemen.

**FFIEC / Industry High-Risk Secrecy / Tax-Haven Jurisdictions — elevated review
required:**
- Cayman Islands, British Virgin Islands (BVI), Panama, Seychelles, Belize, Bahamas,
  Bermuda, Marshall Islands, Liechtenstein, Vanuatu.

**Sanctions overlap:** any entity formed in or substantially operating from a
comprehensive-sanctions jurisdiction (Cuba, Iran, North Korea, Syria, Crimea, Donetsk,
Luhansk regions of Ukraine) is automatically high risk and likely blocked.

---

## [CTA_BOI] Corporate Transparency Act — Beneficial Ownership Information Reporting

**Effective January 1, 2024.** Domestic and foreign reporting companies must file
Beneficial Ownership Information (BOI) with FinCEN within 30 days of formation
(or 30 days of any change). The CTA does *not* replace the FI's CDD obligations
but provides a parallel federal record.

**Reporting beneficial owner under the CTA** = an individual who, directly or
indirectly:
- Exercises **substantial control** over the reporting company (senior officer,
  appointment authority over senior officers/board, direction of important
  decisions), OR
- Owns or controls **≥25%** of the ownership interests.

**For each beneficial owner**, the report must include: full legal name, date of
birth, current residential address, a unique identifying number (US passport,
driver's license, or state ID; for non-US persons, foreign passport plus
country of issuance), and an image of the identifying document.

**Practical FI guidance:** ask the applicant whether the entity has filed its
initial BOI report. If not, document that requirement in the intake checklist.
Cite this section whenever you request a passport, ID image, or BOI
attestation.

---

## [CTA_FOREIGN_REPORTING_CO] CTA — Foreign Reporting Companies

A **foreign reporting company** is any entity formed under the law of a foreign
country that has registered to do business in any U.S. state or tribal
jurisdiction by filing a document with a Secretary of State or similar office.

**BOI obligations** mirror the domestic case (≥25% ownership / substantial
control), with two critical additions an FI should always confirm:

- **Company applicant** identification — the individual who filed the
  registration document on the entity's behalf must also be reported.
- **Foreign-issued identifying documents** are acceptable for non-US
  beneficial owners (foreign passport + country of issuance), but copies must
  be on file.

**FI heuristic:** if the entity is foreign-domiciled (not formed in a U.S.
state) and is opening U.S. operations or a U.S. account, treat it as a foreign
reporting company until proven otherwise. Request: certified copy of the U.S.
state registration filing, full beneficial ownership chart, and an attestation
of nominee/proxy director arrangements (if any).

---

## [APOSTILLE_HAGUE] Apostille / Hague Convention for Foreign Formation Documents

When an applicant submits formation documents issued by a foreign government
(certificate of incorporation, commercial register extract, good-standing
certificate), an FI cannot generally rely on the foreign seal alone.

**Apostille rule:**
- If the issuing country is a party to the **1961 Hague Apostille Convention**
  (UK, Germany, France, Spain, Mexico, Singapore, etc.), the FI should require
  an apostille issued by the foreign country's competent authority — a single
  certificate that authenticates the public document for use in another
  Convention state.
- If the issuing country is **not a party** (e.g. Cayman Islands accession
  status varies, certain offshore jurisdictions), the document must be
  **legalized** through consular channels (foreign-ministry attestation +
  U.S. consulate authentication).

**Translations.** Any non-English document must be accompanied by a certified
English translation. The translator's certification of accuracy should be
notarized.

**Cite this section** when requesting apostilled or legalized formation docs,
or certified translations.

---

## [FOREIGN_NATURAL_PERSON] Identification of Foreign Natural-Person UBOs

When a beneficial owner (≥25% ownership or control prong) is a **non-U.S.
natural person**, CIP under § 1020.220 still applies but the documentary set
expands.

**Required:**
- Foreign passport (unexpired) — note number and country of issuance.
- Evidence of current residential address (foreign utility bill, bank
  statement, or government-issued residency document, ≤3 months old).
- Tax identification: a U.S. **ITIN** if the individual has U.S. tax
  obligations; otherwise a completed **Form W-8BEN** for individuals (or
  W-8BEN-E for entity owners). Document the chosen path in the file.

**Recommended for elevated review:**
- Source-of-funds attestation describing how the individual will fund
  contributions to the entity. Required when wire activity will originate
  outside the U.S. or when the individual is from a high-risk jurisdiction.
- Sanctions and PEP screening on the foreign passport name *and* any local
  transliteration of the name.

**Cite this section** any time you request foreign-individual ID, translation,
W-8/ITIN, or foreign source-of-funds documentation.

---

## [OFFSHORE_JURISDICTION_RISK] Offshore & Multi-Jurisdiction Structure Risk

When the ownership chain crosses an offshore secrecy or low-substance
jurisdiction (Cayman Islands, BVI, Bermuda, Bahamas, Channel Islands,
Luxembourg holding-company SPVs, Marshall Islands, Seychelles, Panama), or
includes a **nominee director / shareholder** arrangement, EDD applies even
absent any sanctions hit.

**Why the FI cares:**
- Offshore entities often obscure the chain to the natural person UBO; the FI
  must affirmatively trace through.
- Nominee arrangements break the link between the named owner of record and
  the economic beneficial owner. The FI must obtain the **declaration of
  trust** or **nominee agreement** identifying the principal.

**Escalation triggers (non-exhaustive). When ≥2 of these are present in a
single applicant, an autonomous agent should request human compliance review
rather than complete the file alone:**
- ≥3 ownership tiers between the applicant and the natural-person UBO.
- ≥3 distinct jurisdictions in the chain, or any offshore intermediary.
- Nominee / proxy director or shareholder arrangement.
- Irrevocable trust intermediary combined with foreign nationals.
- A confirmed or potential sanctions / PEP / adverse-media hit on any UBO.

**Cite this section** when explaining a jurisdiction risk flag, when
requesting a nominee declaration, or when justifying an escalation
recommendation.

---

## [recordkeeping] Recordkeeping & Reporting Adjacent Rules

- **§ 1010.430 — Records of identity:** retain UBO/CIP records for **5 years** after
  account closure.
- **§ 1010.311–.313 — CTRs:** cash transactions >$10,000 reported within 15 days.
- **§ 1020.320 — SARs:** suspicious-activity report within 30 days (60 with no
  identified subject). Threshold $5,000 (banks).

These are not core to UBO resolution but are commonly referenced in the recommendation
section of an EDD memo. Cite when relevant.
