# Seveso Threshold Calculator

A command-line tool to calculate whether your inventory of hazardous goods reaches Seveso Lower Tier (low threshold) or Upper Tier (high threshold) levels based on the **Seveso III Directive (2012/18/EU)**.

## Overview

The Seveso Directive requires establishments holding dangerous substances above certain thresholds to implement safety measures. This tool helps you:

- Track your hazardous goods inventory
- Calculate threshold ratios using the summation rule
- Determine if you fall under Lower Tier or Upper Tier requirements

### The Summation Rule

The Seveso Directive uses a summation rule for determining thresholds:

```
If Σ(quantity / threshold) >= 1, the threshold is reached
```

This means even if individual substances are below their thresholds, the combined effect might still trigger Seveso requirements.

## Installation

```bash
# Clone or copy the script
chmod +x seveso_calculator.py

# Run directly
./seveso_calculator.py

# Or with Python
python3 seveso_calculator.py
```

No external dependencies required - uses only Python standard library.

## Usage

### Interactive Mode

Simply run without arguments:

```bash
./seveso_calculator.py
```

This opens an interactive menu where you can:
1. Add items to inventory
2. View current inventory
3. Calculate thresholds
4. Browse available substances and categories
5. Remove or clear items

### Command Line Mode

#### List available substances and categories

```bash
# List all named substances with thresholds
./seveso_calculator.py --list-substances

# List all hazard categories
./seveso_calculator.py --list-categories
```

#### Manage inventory

```bash
# Add using a named substance
./seveso_calculator.py --add "Tank 1 - Chlorine" 15 --substance chlorine

# Add using a hazard category
./seveso_calculator.py --add "Flammable gas storage" 30 --category P2

# Add with custom thresholds
./seveso_calculator.py --add "Special chemical" 100 --thresholds 50 200

# View inventory
./seveso_calculator.py --list-inventory

# Remove item by index
./seveso_calculator.py --remove 0

# Clear all inventory
./seveso_calculator.py --clear
```

#### Calculate thresholds

```bash
# Standard output
./seveso_calculator.py --calculate

# JSON output for integration
./seveso_calculator.py --calculate --json
```

#### Use a different inventory file

```bash
./seveso_calculator.py -f my_site_inventory.json --calculate
```

## Example Session

```bash
# Add some substances
$ ./seveso_calculator.py --add "Chlorine tank" 8 --substance chlorine
Added: Chlorine tank (8.0 tonnes)

$ ./seveso_calculator.py --add "LPG storage" 120 --substance lpg
Added: LPG storage (120.0 tonnes)

$ ./seveso_calculator.py --add "Diesel fuel" 1500 --substance diesel
Added: Diesel fuel (1500.0 tonnes)

# Calculate thresholds
$ ./seveso_calculator.py --calculate

============================================================
  SEVESO THRESHOLD CALCULATION RESULTS
============================================================

--- Item Breakdown ---
Name                           Qty        Lower%       Upper%
----------------------------------------------------------------------
Chlorine tank                  8.00       80.0         32.0
LPG storage                    120.00     240.0        60.0
Diesel fuel                    1500.00    60.0         6.0
----------------------------------------------------------------------
TOTAL                                     380.0        98.0

--- Summary ---
Lower Tier Ratio: 3.8000 (380.00%)
Upper Tier Ratio: 0.9800 (98.00%)

--- Seveso Status ---
  LOWER TIER (LOW THRESHOLD) REACHED
    Your establishment falls under Seveso Lower Tier requirements.
    Major accident prevention policy required.
```

## Substance Database

The tool includes thresholds for:

### Named Substances (Annex I Part 2)
Common industrial chemicals including:
- Chlorine, Bromine, Fluorine
- Ammonia, Hydrogen sulfide
- LPG, Natural gas, Hydrogen
- Methanol, Ethylene oxide
- Diesel, Gasoline, Crude oil
- Ammonium nitrate (various grades)
- And many more...

### Hazard Categories (Annex I Part 1)
- **H1-H3**: Health hazards (acute toxic, STOT)
- **P1-P8**: Physical hazards (explosives, flammables, oxidizers)
- **E1-E2**: Environmental hazards (aquatic toxicity)
- **O1-O3**: Other hazards (reactive substances)

## Output Formats

### Standard Output
Human-readable formatted tables with:
- Item breakdown showing individual contributions
- Total percentages for lower and upper tiers
- Clear status indicator

### JSON Output
Use `--json` flag for machine-readable output:

```json
{
  "lower_ratio": 3.8,
  "upper_ratio": 0.98,
  "lower_tier_reached": true,
  "upper_tier_reached": false,
  "lower_percentage": 380.0,
  "upper_percentage": 98.0,
  "items": [...]
}
```

## Data Storage

Inventory is stored in JSON format (default: `seveso_inventory.json`). You can maintain multiple inventory files for different sites using the `-f` flag.

## Regulatory Background

The Seveso III Directive (2012/18/EU) establishes two tiers:

- **Lower Tier**: Requires a Major Accident Prevention Policy (MAPP)
- **Upper Tier**: Requires full Safety Report, Internal Emergency Plan, and information for External Emergency Plans

## Disclaimer

This tool is provided for informational purposes. Always consult official regulatory guidance and qualified professionals for compliance decisions. Thresholds may vary by jurisdiction and specific circumstances.

## License

MIT License
