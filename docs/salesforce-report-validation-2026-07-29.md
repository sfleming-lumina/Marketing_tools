# Salesforce report validation

**Audit date:** 2026-07-29

**Salesforce org:** Lumina Solar, Inc. production

**Purpose:** Validate marketing-dashboard definitions, geography grouping, test-data treatment, and source semantics against actively used Salesforce reports.

## Report inventory

Two hundred recently run reports with Lead, Campaign, Set Rate, Run Rate, Win, or Marketing in the report name were reviewed.

The most relevant report families are concentrated in:

| Folder | Reports in reviewed inventory |
|---|---:|
| RevOps Reports | 134 |
| Hannah Reports | 25 |
| MD Marketing | 10 |
| Public Reports | 9 |
| Sales & Marketing Dashboards Reports | 5 |
| ELT Reports | 4 |

The inventory contains separate Salesforce views for campaign members, campaign spend, set rate, run rate, wins, state, campaign, and recent-period scorecards. These views do not all share the same date field or denominator.

## Solar Reviews source validation

### SolarReviews Leads by County YTD

- Report ID: `00OTV00000DdOpN2AV`
- Folder: `Hannah Reports`
- Report type: Campaigns with Campaign Members
- Format: Summary
- Last modified: 2026-07-28
- Last run during audit: 2026-07-29

Current Salesforce result:

| Metric | Value |
|---|---:|
| Campaign-member rows | 6,915 |
| Converted | 984 |
| Set rate | 14.23% |
| DMV bucket rows returned | 3,416 |
| DMV converted | 546 |
| DMV set rate | 15.98% |

The report's exact set-rate formula is:

```text
SUM(CampaignMember.Converted__c) / RowCount
```

Important filters:

- Campaign name equals `SolarReviews`.
- Member Status Update Date equals `THIS YEAR`.
- First name does not contain `test`.
- Last name does not contain `test`.
- Email does not contain `@luminasolar.com`.
- County contains a PA, DE, MD, VA, or DC suffix.

This is not a lead-created cohort. A record enters the report based on member status-update date, and its denominator is campaign-member rows. Dashboard lead-cohort totals should therefore not be expected to match this report exactly.

The report uses a custom presentation bucket:

- DMV: Maryland, MD, Virginia, VA, DC
- PA/DE: PA, Pennsylvania, DE, Delaware

This bucket is useful for report display but is not the authoritative operational field.

## Operational region validation

The actively used `Ryan Monthly Install kW by Ops Region` report:

- Report ID: `00OTV00000Oj8Mz2AJ`
- Groups directly on `Solar_Work_Order__c.Ops_Region__c`
- Returns the operational values `MD` and `PA` in every 2026 month reviewed

The dashboard now follows those operational values:

- **Maryland** = `MD` Ops Region. When Ops Region is missing, MD/DC/VA states are the fallback.
- **Pennsylvania** = `PA` Ops Region. When Ops Region is missing, PA/DE states are the fallback.
- **Outside operating footprint** = a resolved Ops Region or state that maps to neither MD nor PA.
- **Unresolved** = no usable Ops Region or state fallback.

This intentionally replaces the UI label DMV with Maryland while still keeping DC and Virginia activity assigned to the operational MD region.

## Campaign member and spend validation

### 2026 Campaign Member Data_MR

- Report ID: `00OTV00000LiKN72AN`
- Current rows: 13,539
- Date field: Member Status Update Date
- Test treatment: excludes first/last name containing `test` and internal Lumina email addresses

### 2026 Campaign Spend Data_MR

- Report ID: `00OTV00000LlxtN2AR`
- Current rows: 78
- Date field: Campaign Spend Date

These reports confirm that member activity and spend are independently dated sources. Spend should not be assumed complete merely because member activity is present.

## Set and run rate validation

### Set Rate by State_2026_3PV

- Report ID: `00OTV00000RWaU12AL`
- Campaign-member rows: 9,490
- Converted: 1,249
- Published set rate: 13%
- Formula: `SUM(CampaignMember.Converted__c) / RowCount`
- Grouping: Campaign × Campaign Member State
- Date field: Member Status Update Date

### Run Rate by State_2026_3PV

- Report ID: `00OTV00000RWaTx2AL`
- Opportunity rows: 1,211
- Runs: 951
- Published run rate: 79%
- Formula: `SUM(Opportunity.Runs__c) / RowCount`
- Grouping: Campaign Source × Opportunity State
- Population: Residential opportunities with survey status Complete or Did Not Run

The numerator and denominator change between the Salesforce set-rate and run-rate reports. The dashboard's fixed lead-cohort funnel is more suitable for following one acquisition population end-to-end, while these Salesforce reports remain valuable operational checks for their individual stages.

## Approach changes informed by Salesforce

1. Use the authoritative Ops Region field before state-name fallback.
2. Label the regions Maryland and Pennsylvania in the product.
3. Treat Delaware as part of PA Ops when operationally assigned or when Ops Region is missing.
4. Keep Salesforce event/status-date reports as validation lenses, not force them into cohort parity.
5. Document the denominator beside rate metrics and in the usage guide.
6. Preserve explicit test exclusions and add a future governed rule for internal-email/test-name exclusions where those fields are available in the curated source.
