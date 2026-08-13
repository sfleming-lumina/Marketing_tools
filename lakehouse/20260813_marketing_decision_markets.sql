CREATE TABLE IF NOT EXISTS
  `lumina-lakehouse.marketing_tool_ops.dim_marketing_decision_market` (
    state_code STRING NOT NULL,
    county_match_name STRING NOT NULL,
    decision_market_key STRING NOT NULL,
    decision_market_name STRING NOT NULL,
    operating_region STRING NOT NULL,
    effective_start_date DATE NOT NULL,
    effective_end_date DATE,
    is_current BOOL NOT NULL,
    mapping_version STRING NOT NULL,
    mapping_reason STRING,
    mapping_owner STRING,
    updated_at TIMESTAMP NOT NULL
  )
CLUSTER BY is_current, operating_region, state_code, decision_market_key;

CREATE TEMP TABLE decision_market_seed AS
WITH market_definitions AS (
  SELECT *
  FROM UNNEST([
    STRUCT('MD' AS state_code, 'BALTIMORE METRO' AS decision_market_key, 'Baltimore Metro' AS decision_market_name, 'Maryland' AS operating_region, ['BALTIMORE','BALTIMORE CITY','BALTIMORE COUNTY','ANNE ARUNDEL','ANNE ARUNDEL COUNTY','HOWARD','HOWARD COUNTY','HARFORD','HARFORD COUNTY','CARROLL','CARROLL COUNTY'] AS county_match_names),
    STRUCT('MD', 'DC NORTH WEST', 'DC North / West', 'Maryland', ['MONTGOMERY','MONTGOMERY COUNTY','FREDERICK','FREDERICK COUNTY']),
    STRUCT('MD', 'DC EAST SOUTH', 'DC East / South', 'Maryland', ['PRINCE GEORGE S','PRINCE GEORGES','PRINCE GEORGE S COUNTY','PRINCE GEORGES COUNTY','CHARLES','CHARLES COUNTY','CALVERT','CALVERT COUNTY','ST MARY S','ST MARYS','ST MARY S COUNTY','ST MARYS COUNTY']),
    STRUCT('MD', 'MARYLAND EASTERN SHORE', 'Maryland Eastern Shore', 'Maryland', ['CECIL','CECIL COUNTY','KENT','KENT COUNTY','QUEEN ANNE S','QUEEN ANNES','QUEEN ANNE S COUNTY','QUEEN ANNES COUNTY','CAROLINE','CAROLINE COUNTY','TALBOT','TALBOT COUNTY','DORCHESTER','DORCHESTER COUNTY','WICOMICO','WICOMICO COUNTY','WORCESTER','WORCESTER COUNTY','SOMERSET','SOMERSET COUNTY']),
    STRUCT('MD', 'WESTERN MARYLAND', 'Western Maryland', 'Maryland', ['WASHINGTON','WASHINGTON COUNTY','ALLEGANY','ALLEGANY COUNTY','GARRETT','GARRETT COUNTY']),
    STRUCT('DC', 'DISTRICT OF COLUMBIA', 'District of Columbia', 'Maryland', ['DISTRICT OF COLUMBIA','WASHINGTON DC','WASHINGTON']),
    STRUCT('VA', 'NORTHERN VIRGINIA', 'Northern Virginia', 'Maryland', ['ARLINGTON','ARLINGTON COUNTY','ALEXANDRIA','CITY OF ALEXANDRIA','FAIRFAX','FAIRFAX COUNTY','CITY OF FAIRFAX','FALLS CHURCH','CITY OF FALLS CHURCH','LOUDOUN','LOUDOUN COUNTY','PRINCE WILLIAM','PRINCE WILLIAM COUNTY','MANASSAS','CITY OF MANASSAS','MANASSAS PARK','CITY OF MANASSAS PARK','STAFFORD','STAFFORD COUNTY','FAUQUIER','FAUQUIER COUNTY']),
    STRUCT('PA', 'PHILADELPHIA METRO', 'Philadelphia Metro', 'Pennsylvania', ['PHILADELPHIA','PHILADELPHIA COUNTY','BUCKS','BUCKS COUNTY','MONTGOMERY','MONTGOMERY COUNTY','CHESTER','CHESTER COUNTY','DELAWARE','DELAWARE COUNTY']),
    STRUCT('PA', 'SOUTH CENTRAL PA', 'South Central PA', 'Pennsylvania', ['YORK','YORK COUNTY','ADAMS','ADAMS COUNTY','CUMBERLAND','CUMBERLAND COUNTY','FRANKLIN','FRANKLIN COUNTY']),
    STRUCT('PA', 'HARRISBURG LANCASTER', 'Harrisburg / Lancaster', 'Pennsylvania', ['DAUPHIN','DAUPHIN COUNTY','LEBANON','LEBANON COUNTY','LANCASTER','LANCASTER COUNTY','PERRY','PERRY COUNTY']),
    STRUCT('PA', 'LEHIGH VALLEY', 'Lehigh Valley', 'Pennsylvania', ['LEHIGH','LEHIGH COUNTY','NORTHAMPTON','NORTHAMPTON COUNTY']),
    STRUCT('PA', 'NORTHEAST PA', 'Northeast PA', 'Pennsylvania', ['LACKAWANNA','LACKAWANNA COUNTY','LUZERNE','LUZERNE COUNTY','MONROE','MONROE COUNTY','PIKE','PIKE COUNTY','WAYNE','WAYNE COUNTY','CARBON','CARBON COUNTY']),
    STRUCT('PA', 'BERKS SCHUYLKILL', 'Berks / Schuylkill', 'Pennsylvania', ['BERKS','BERKS COUNTY','SCHUYLKILL','SCHUYLKILL COUNTY']),
    STRUCT('PA', 'CENTRAL PA', 'Central PA', 'Pennsylvania', ['CENTRE','CENTRE COUNTY','MIFFLIN','MIFFLIN COUNTY','JUNIATA','JUNIATA COUNTY','SNYDER','SNYDER COUNTY','UNION','UNION COUNTY','NORTHUMBERLAND','NORTHUMBERLAND COUNTY']),
    STRUCT('DE', 'DELAWARE', 'Delaware', 'Pennsylvania', ['NEW CASTLE','NEW CASTLE COUNTY','KENT','KENT COUNTY','SUSSEX','SUSSEX COUNTY'])
  ])
)

SELECT
  state_code,
  county_match_name,
  decision_market_key,
  decision_market_name,
  operating_region,
  DATE '2026-08-13' AS effective_start_date,
  CAST(NULL AS DATE) AS effective_end_date,
  TRUE AS is_current,
  'seed_v1' AS mapping_version,
  'Contiguous, leadership-recognizable market below Ops-region grain; review quarterly with Marketing and Sales Ops.' AS mapping_reason,
  'Marketing Intelligence' AS mapping_owner,
  CURRENT_TIMESTAMP() AS updated_at
FROM market_definitions
CROSS JOIN UNNEST(county_match_names) AS county_match_name;

-- A new mapping version closes the previous rows without deleting history.
-- Changes to the governed membership must therefore ship with a new version
-- and effective-start date in the seed above.
UPDATE `lumina-lakehouse.marketing_tool_ops.dim_marketing_decision_market`
SET
  is_current = FALSE,
  effective_end_date = DATE_SUB(DATE '2026-08-13', INTERVAL 1 DAY),
  updated_at = CURRENT_TIMESTAMP()
WHERE is_current
  AND mapping_version != 'seed_v1';

MERGE `lumina-lakehouse.marketing_tool_ops.dim_marketing_decision_market` AS target
USING decision_market_seed AS source
ON target.state_code = source.state_code
 AND target.county_match_name = source.county_match_name
 AND target.mapping_version = source.mapping_version
WHEN MATCHED THEN UPDATE SET
  decision_market_key = source.decision_market_key,
  decision_market_name = source.decision_market_name,
  operating_region = source.operating_region,
  effective_start_date = source.effective_start_date,
  effective_end_date = source.effective_end_date,
  is_current = source.is_current,
  mapping_reason = source.mapping_reason,
  mapping_owner = source.mapping_owner,
  updated_at = source.updated_at
WHEN NOT MATCHED THEN INSERT ROW;

ASSERT (
  SELECT COUNT(*) = COUNT(DISTINCT CONCAT(state_code, '|', county_match_name))
  FROM `lumina-lakehouse.marketing_tool_ops.dim_marketing_decision_market`
  WHERE is_current
) AS 'Decision-market mapping contains duplicate current state/county keys';

ASSERT (
  SELECT COUNT(DISTINCT decision_market_key)
  FROM `lumina-lakehouse.marketing_tool_ops.dim_marketing_decision_market`
  WHERE is_current
) >= 10 AS 'Decision-market mapping is unexpectedly small';

ASSERT (
  SELECT COUNTIF(
    (state_code IN ('MD', 'DC', 'VA') AND operating_region != 'Maryland')
    OR (state_code IN ('PA', 'DE') AND operating_region != 'Pennsylvania')
  ) = 0
  FROM `lumina-lakehouse.marketing_tool_ops.dim_marketing_decision_market`
  WHERE is_current
) AS 'Decision-market mapping crosses governed Ops-region boundaries';
