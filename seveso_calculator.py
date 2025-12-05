#!/usr/bin/env python3
"""
Seveso Threshold Calculator

A tool to calculate whether your inventory of hazardous goods reaches
Seveso lower tier (low threshold) or upper tier (high threshold) levels
based on the Seveso III Directive (2012/18/EU).

The summation rule is applied:
- If Σ(quantity/threshold) >= 1, the threshold is reached
"""

import json
import os
import sys
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional
from pathlib import Path


class HazardCategory(Enum):
    """Seveso III Directive hazard categories (Annex I Part 1)"""
    # Health hazards
    H1 = "Acute toxic category 1 (all exposure routes)"
    H2 = "Acute toxic category 2 (all exposure routes) and category 3 (inhalation)"
    H3 = "STOT SE category 1"

    # Physical hazards
    P1a = "Explosives, unstable or divisions 1.1-1.4, 1.5, 1.6"
    P1b = "Explosives, divisions 1.1-1.4, 1.5, 1.6 (less stringent)"
    P2 = "Flammable gases category 1 or 2"
    P3a = "Flammable aerosols category 1 or 2 (flammable gas/liquid)"
    P3b = "Flammable aerosols category 1 or 2 (not P3a)"
    P4 = "Oxidising gases category 1"
    P5a = "Flammable liquids category 1, or cat 2/3 at elevated temp"
    P5b = "Flammable liquids category 2 or 3 (not P5a)"
    P5c = "Flammable liquids category 2 or 3 (special processes)"
    P6a = "Self-reactive substances/mixtures type A or B"
    P6b = "Self-reactive substances/mixtures type C, D, E or F"
    P7 = "Pyrophoric liquids/solids category 1"
    P8 = "Oxidising liquids/solids category 1, 2 or 3"

    # Environmental hazards
    E1 = "Hazardous to aquatic environment acute 1 or chronic 1"
    E2 = "Hazardous to aquatic environment chronic 2"

    # Other hazards
    O1 = "Substances/mixtures with EUH014"
    O2 = "Substances/mixtures reacting with water (EUH029)"
    O3 = "Substances/mixtures with EUH032"


# Category thresholds in tonnes (Annex I Part 1)
CATEGORY_THRESHOLDS = {
    HazardCategory.H1: {"lower": 5, "upper": 20},
    HazardCategory.H2: {"lower": 50, "upper": 200},
    HazardCategory.H3: {"lower": 50, "upper": 200},
    HazardCategory.P1a: {"lower": 10, "upper": 50},
    HazardCategory.P1b: {"lower": 50, "upper": 200},
    HazardCategory.P2: {"lower": 10, "upper": 50},
    HazardCategory.P3a: {"lower": 150, "upper": 500},
    HazardCategory.P3b: {"lower": 5000, "upper": 50000},
    HazardCategory.P4: {"lower": 50, "upper": 200},
    HazardCategory.P5a: {"lower": 10, "upper": 50},
    HazardCategory.P5b: {"lower": 50, "upper": 200},
    HazardCategory.P5c: {"lower": 5000, "upper": 50000},
    HazardCategory.P6a: {"lower": 10, "upper": 50},
    HazardCategory.P6b: {"lower": 50, "upper": 200},
    HazardCategory.P7: {"lower": 50, "upper": 200},
    HazardCategory.P8: {"lower": 50, "upper": 200},
    HazardCategory.E1: {"lower": 100, "upper": 200},
    HazardCategory.E2: {"lower": 200, "upper": 500},
    HazardCategory.O1: {"lower": 100, "upper": 500},
    HazardCategory.O2: {"lower": 100, "upper": 500},
    HazardCategory.O3: {"lower": 50, "upper": 200},
}


@dataclass
class NamedSubstance:
    """Named substance from Seveso III Directive Annex I Part 2"""
    name: str
    cas_number: Optional[str]
    lower_threshold: float  # in tonnes
    upper_threshold: float  # in tonnes
    notes: str = ""


# Named substances (Annex I Part 2) - Selected common substances
NAMED_SUBSTANCES = {
    "ammonium_nitrate_1": NamedSubstance(
        "Ammonium nitrate (fertilizer grade)", None, 5000, 10000,
        "Capable of self-sustaining decomposition"
    ),
    "ammonium_nitrate_2": NamedSubstance(
        "Ammonium nitrate (technical grade)", None, 1250, 5000,
        "Fertilizer with >28% nitrogen from AN"
    ),
    "ammonium_nitrate_3": NamedSubstance(
        "Ammonium nitrate (off-spec/rejected)", None, 350, 2500,
        "Failed detonation test"
    ),
    "ammonium_nitrate_4": NamedSubstance(
        "Ammonium nitrate (high hazard)", None, 10, 50,
        "UN 0222 or heating decomposition"
    ),
    "potassium_nitrate": NamedSubstance(
        "Potassium nitrate", "7757-79-1", 5000, 10000,
        "Prilled/granulated fertilizer"
    ),
    "arsenic_pentoxide": NamedSubstance(
        "Arsenic pentoxide", "1303-28-2", 1, 2, ""
    ),
    "arsenic_trioxide": NamedSubstance(
        "Arsenic trioxide", "1327-53-3", 0.1, 0.1, ""
    ),
    "bromine": NamedSubstance(
        "Bromine", "7726-95-6", 20, 100, ""
    ),
    "chlorine": NamedSubstance(
        "Chlorine", "7782-50-5", 10, 25, ""
    ),
    "nickel_compounds": NamedSubstance(
        "Nickel compounds (inhalable powder)", None, 1, 1,
        "Carcinogenic category 1A/1B"
    ),
    "ethylene_oxide": NamedSubstance(
        "Ethylene oxide", "75-21-8", 5, 50, ""
    ),
    "fluorine": NamedSubstance(
        "Fluorine", "7782-41-4", 10, 20, ""
    ),
    "formaldehyde": NamedSubstance(
        "Formaldehyde (≥90%)", "50-00-0", 5, 50, ""
    ),
    "hydrogen": NamedSubstance(
        "Hydrogen", "1333-74-0", 5, 50, ""
    ),
    "hydrogen_chloride": NamedSubstance(
        "Hydrogen chloride (liquefied)", "7647-01-0", 25, 250, ""
    ),
    "lead_alkyls": NamedSubstance(
        "Lead alkyls", None, 5, 50, ""
    ),
    "lpg": NamedSubstance(
        "Liquefied petroleum gas (LPG)", None, 50, 200,
        "Including commercial propane/butane"
    ),
    "methanol": NamedSubstance(
        "Methanol", "67-56-1", 500, 5000, ""
    ),
    "acetylene": NamedSubstance(
        "Acetylene", "74-86-2", 5, 50, ""
    ),
    "natural_gas": NamedSubstance(
        "Natural gas", None, 50, 200, "Gasified LNG included"
    ),
    "oxygen": NamedSubstance(
        "Oxygen", "7782-44-7", 200, 2000, ""
    ),
    "sulfur_dioxide": NamedSubstance(
        "Sulfur dioxide", "7446-09-5", 20, 200, ""
    ),
    "sulfur_trioxide": NamedSubstance(
        "Sulfur trioxide", "7446-11-9", 15, 75, ""
    ),
    "toluene_diisocyanate": NamedSubstance(
        "Toluene diisocyanate", None, 10, 100, ""
    ),
    "carbonyl_chloride": NamedSubstance(
        "Carbonyl chloride (phosgene)", "75-44-5", 0.3, 0.75, ""
    ),
    "ammonia_anhydrous": NamedSubstance(
        "Ammonia (anhydrous)", "7664-41-7", 50, 200, ""
    ),
    "boron_trifluoride": NamedSubstance(
        "Boron trifluoride", "7637-07-2", 5, 20, ""
    ),
    "hydrogen_sulfide": NamedSubstance(
        "Hydrogen sulfide", "7783-06-4", 5, 20, ""
    ),
    "piperidine": NamedSubstance(
        "Piperidine", "110-89-4", 50, 200, ""
    ),
    "diesel": NamedSubstance(
        "Diesel/gas oil/heating oil", None, 2500, 25000,
        "Includes kerosene, jet fuel"
    ),
    "gasoline": NamedSubstance(
        "Gasoline and petrol", None, 2500, 25000, ""
    ),
    "heavy_fuel_oil": NamedSubstance(
        "Heavy fuel oil", None, 2500, 25000, ""
    ),
    "crude_oil": NamedSubstance(
        "Crude oil", None, 2500, 25000, ""
    ),
}


@dataclass
class InventoryItem:
    """An item in the hazardous goods inventory"""
    name: str
    quantity: float  # in tonnes
    substance_key: Optional[str] = None  # key in NAMED_SUBSTANCES
    category: Optional[str] = None  # HazardCategory name
    custom_lower_threshold: Optional[float] = None
    custom_upper_threshold: Optional[float] = None

    def get_thresholds(self) -> tuple[float, float]:
        """Get (lower, upper) thresholds for this item"""
        if self.custom_lower_threshold is not None and self.custom_upper_threshold is not None:
            return self.custom_lower_threshold, self.custom_upper_threshold

        if self.substance_key and self.substance_key in NAMED_SUBSTANCES:
            sub = NAMED_SUBSTANCES[self.substance_key]
            return sub.lower_threshold, sub.upper_threshold

        if self.category:
            try:
                cat = HazardCategory[self.category]
                thresholds = CATEGORY_THRESHOLDS[cat]
                return thresholds["lower"], thresholds["upper"]
            except KeyError:
                pass

        raise ValueError(f"Cannot determine thresholds for {self.name}")


class SeveroCalculator:
    """Calculator for Seveso threshold assessments"""

    def __init__(self, inventory_file: str = "seveso_inventory.json"):
        self.inventory_file = Path(inventory_file)
        self.inventory: list[InventoryItem] = []
        self.load_inventory()

    def load_inventory(self) -> None:
        """Load inventory from file"""
        if self.inventory_file.exists():
            with open(self.inventory_file, 'r') as f:
                data = json.load(f)
                self.inventory = [InventoryItem(**item) for item in data]

    def save_inventory(self) -> None:
        """Save inventory to file"""
        with open(self.inventory_file, 'w') as f:
            json.dump([asdict(item) for item in self.inventory], f, indent=2)

    def add_item(self, item: InventoryItem) -> None:
        """Add an item to inventory"""
        self.inventory.append(item)
        self.save_inventory()

    def remove_item(self, index: int) -> None:
        """Remove an item from inventory by index"""
        if 0 <= index < len(self.inventory):
            del self.inventory[index]
            self.save_inventory()

    def clear_inventory(self) -> None:
        """Clear all inventory items"""
        self.inventory = []
        self.save_inventory()

    def calculate_ratios(self) -> dict:
        """
        Calculate the summation ratios for lower and upper thresholds.

        Returns dict with:
        - lower_ratio: sum of (quantity/lower_threshold) for all items
        - upper_ratio: sum of (quantity/upper_threshold) for all items
        - items: list of item details with individual ratios
        - lower_tier_reached: bool
        - upper_tier_reached: bool
        """
        lower_sum = 0.0
        upper_sum = 0.0
        item_details = []

        for item in self.inventory:
            try:
                lower_thresh, upper_thresh = item.get_thresholds()
                lower_ratio = item.quantity / lower_thresh
                upper_ratio = item.quantity / upper_thresh

                lower_sum += lower_ratio
                upper_sum += upper_ratio

                item_details.append({
                    "name": item.name,
                    "quantity": item.quantity,
                    "lower_threshold": lower_thresh,
                    "upper_threshold": upper_thresh,
                    "lower_ratio": lower_ratio,
                    "upper_ratio": upper_ratio,
                    "lower_percentage": lower_ratio * 100,
                    "upper_percentage": upper_ratio * 100,
                })
            except ValueError as e:
                item_details.append({
                    "name": item.name,
                    "quantity": item.quantity,
                    "error": str(e)
                })

        return {
            "lower_ratio": lower_sum,
            "upper_ratio": upper_sum,
            "lower_tier_reached": lower_sum >= 1.0,
            "upper_tier_reached": upper_sum >= 1.0,
            "lower_percentage": lower_sum * 100,
            "upper_percentage": upper_sum * 100,
            "items": item_details,
        }


def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)


def print_substances() -> None:
    """Print available named substances"""
    print_header("AVAILABLE NAMED SUBSTANCES")
    print(f"\n{'Key':<25} {'Name':<35} {'Lower':<10} {'Upper':<10}")
    print("-" * 80)
    for key, sub in sorted(NAMED_SUBSTANCES.items()):
        print(f"{key:<25} {sub.name[:35]:<35} {sub.lower_threshold:<10} {sub.upper_threshold:<10}")


def print_categories() -> None:
    """Print available hazard categories"""
    print_header("AVAILABLE HAZARD CATEGORIES")
    print(f"\n{'Category':<10} {'Description':<45} {'Lower':<10} {'Upper':<10}")
    print("-" * 80)
    for cat in HazardCategory:
        thresholds = CATEGORY_THRESHOLDS[cat]
        desc = cat.value[:45] if len(cat.value) > 45 else cat.value
        print(f"{cat.name:<10} {desc:<45} {thresholds['lower']:<10} {thresholds['upper']:<10}")


def print_inventory(calc: SeveroCalculator) -> None:
    """Print current inventory"""
    print_header("CURRENT INVENTORY")
    if not calc.inventory:
        print("\nInventory is empty.")
        return

    print(f"\n{'#':<4} {'Name':<30} {'Quantity':<12} {'Type':<20}")
    print("-" * 70)
    for i, item in enumerate(calc.inventory):
        type_str = item.substance_key or item.category or "Custom"
        print(f"{i:<4} {item.name[:30]:<30} {item.quantity:<12.2f} {type_str:<20}")


def print_results(results: dict) -> None:
    """Print calculation results"""
    print_header("SEVESO THRESHOLD CALCULATION RESULTS")

    # Print item breakdown
    print("\n--- Item Breakdown ---")
    print(f"{'Name':<30} {'Qty':<10} {'Lower%':<12} {'Upper%':<12}")
    print("-" * 70)

    for item in results['items']:
        if 'error' in item:
            print(f"{item['name'][:30]:<30} {item['quantity']:<10.2f} ERROR: {item['error']}")
        else:
            print(f"{item['name'][:30]:<30} {item['quantity']:<10.2f} "
                  f"{item['lower_percentage']:<12.1f} {item['upper_percentage']:<12.1f}")

    print("-" * 70)
    print(f"{'TOTAL':<30} {'':<10} "
          f"{results['lower_percentage']:<12.1f} {results['upper_percentage']:<12.1f}")

    # Print summary
    print("\n--- Summary ---")
    print(f"Lower Tier Ratio: {results['lower_ratio']:.4f} ({results['lower_percentage']:.2f}%)")
    print(f"Upper Tier Ratio: {results['upper_ratio']:.4f} ({results['upper_percentage']:.2f}%)")

    print("\n--- Seveso Status ---")
    if results['upper_tier_reached']:
        print("⚠️  UPPER TIER (HIGH THRESHOLD) REACHED")
        print("    Your establishment falls under Seveso Upper Tier requirements.")
        print("    Full safety report and emergency plans required.")
    elif results['lower_tier_reached']:
        print("⚠️  LOWER TIER (LOW THRESHOLD) REACHED")
        print("    Your establishment falls under Seveso Lower Tier requirements.")
        print("    Major accident prevention policy required.")
    else:
        print("✓  Below Seveso thresholds")
        print(f"    Lower tier: {100 - results['lower_percentage']:.1f}% capacity remaining")
        print(f"    Upper tier: {100 - results['upper_percentage']:.1f}% capacity remaining")


def interactive_add(calc: SeveroCalculator) -> None:
    """Interactive mode to add an item"""
    print("\nAdd new inventory item")
    print("1. Named substance")
    print("2. Hazard category")
    print("3. Custom thresholds")

    choice = input("\nSelect type [1-3]: ").strip()

    name = input("Enter item name/description: ").strip()
    quantity = float(input("Enter quantity (tonnes): ").strip())

    if choice == "1":
        print_substances()
        substance_key = input("\nEnter substance key: ").strip()
        if substance_key not in NAMED_SUBSTANCES:
            print("Invalid substance key!")
            return
        item = InventoryItem(name=name, quantity=quantity, substance_key=substance_key)

    elif choice == "2":
        print_categories()
        category = input("\nEnter category (e.g., H1, P2, E1): ").strip().upper()
        try:
            HazardCategory[category]
        except KeyError:
            print("Invalid category!")
            return
        item = InventoryItem(name=name, quantity=quantity, category=category)

    elif choice == "3":
        lower = float(input("Enter lower threshold (tonnes): ").strip())
        upper = float(input("Enter upper threshold (tonnes): ").strip())
        item = InventoryItem(
            name=name, quantity=quantity,
            custom_lower_threshold=lower, custom_upper_threshold=upper
        )
    else:
        print("Invalid choice!")
        return

    calc.add_item(item)
    print(f"Added: {name} ({quantity} tonnes)")


def main():
    """Main CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Seveso Threshold Calculator - Calculate if your hazardous goods inventory reaches Seveso thresholds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Interactive mode
  %(prog)s --list-substances        # List all named substances
  %(prog)s --list-categories        # List all hazard categories
  %(prog)s --calculate              # Calculate current inventory
  %(prog)s --add "Chlorine" 15 --substance chlorine
  %(prog)s --add "Flammable gas" 30 --category P2
  %(prog)s --add "Custom item" 100 --thresholds 50 200
        """
    )

    parser.add_argument('--inventory-file', '-f', default='seveso_inventory.json',
                        help='Inventory file path (default: seveso_inventory.json)')
    parser.add_argument('--list-substances', '-s', action='store_true',
                        help='List available named substances')
    parser.add_argument('--list-categories', '-c', action='store_true',
                        help='List available hazard categories')
    parser.add_argument('--list-inventory', '-l', action='store_true',
                        help='List current inventory')
    parser.add_argument('--calculate', '-x', action='store_true',
                        help='Calculate Seveso thresholds')
    parser.add_argument('--add', '-a', nargs=2, metavar=('NAME', 'QUANTITY'),
                        help='Add item: name and quantity in tonnes')
    parser.add_argument('--substance', help='Substance key for --add')
    parser.add_argument('--category', help='Hazard category for --add')
    parser.add_argument('--thresholds', nargs=2, type=float, metavar=('LOWER', 'UPPER'),
                        help='Custom thresholds for --add')
    parser.add_argument('--remove', '-r', type=int, metavar='INDEX',
                        help='Remove item by index')
    parser.add_argument('--clear', action='store_true',
                        help='Clear all inventory')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Interactive mode')
    parser.add_argument('--json', '-j', action='store_true',
                        help='Output results as JSON')

    args = parser.parse_args()

    calc = SeveroCalculator(args.inventory_file)

    # Handle list commands
    if args.list_substances:
        print_substances()
        return

    if args.list_categories:
        print_categories()
        return

    if args.list_inventory:
        print_inventory(calc)
        return

    # Handle add command
    if args.add:
        name, quantity = args.add[0], float(args.add[1])

        if args.substance:
            if args.substance not in NAMED_SUBSTANCES:
                print(f"Error: Unknown substance '{args.substance}'")
                sys.exit(1)
            item = InventoryItem(name=name, quantity=quantity, substance_key=args.substance)
        elif args.category:
            try:
                HazardCategory[args.category.upper()]
            except KeyError:
                print(f"Error: Unknown category '{args.category}'")
                sys.exit(1)
            item = InventoryItem(name=name, quantity=quantity, category=args.category.upper())
        elif args.thresholds:
            item = InventoryItem(
                name=name, quantity=quantity,
                custom_lower_threshold=args.thresholds[0],
                custom_upper_threshold=args.thresholds[1]
            )
        else:
            print("Error: --add requires --substance, --category, or --thresholds")
            sys.exit(1)

        calc.add_item(item)
        print(f"Added: {name} ({quantity} tonnes)")
        return

    # Handle remove command
    if args.remove is not None:
        if 0 <= args.remove < len(calc.inventory):
            removed = calc.inventory[args.remove].name
            calc.remove_item(args.remove)
            print(f"Removed: {removed}")
        else:
            print(f"Error: Invalid index {args.remove}")
            sys.exit(1)
        return

    # Handle clear command
    if args.clear:
        calc.clear_inventory()
        print("Inventory cleared.")
        return

    # Handle calculate command
    if args.calculate:
        if not calc.inventory:
            print("Inventory is empty. Add items first.")
            sys.exit(1)

        results = calc.calculate_ratios()

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_results(results)
        return

    # Interactive mode (default if no args)
    if args.interactive or len(sys.argv) == 1:
        print_header("SEVESO THRESHOLD CALCULATOR")
        print("\nThis tool helps determine if your hazardous goods inventory")
        print("reaches Seveso Lower Tier or Upper Tier thresholds.")

        while True:
            print("\n--- Menu ---")
            print("1. Add item to inventory")
            print("2. View inventory")
            print("3. Calculate thresholds")
            print("4. List named substances")
            print("5. List hazard categories")
            print("6. Remove item")
            print("7. Clear inventory")
            print("8. Exit")

            choice = input("\nSelect option [1-8]: ").strip()

            if choice == "1":
                interactive_add(calc)
            elif choice == "2":
                print_inventory(calc)
            elif choice == "3":
                if calc.inventory:
                    results = calc.calculate_ratios()
                    print_results(results)
                else:
                    print("\nInventory is empty. Add items first.")
            elif choice == "4":
                print_substances()
            elif choice == "5":
                print_categories()
            elif choice == "6":
                print_inventory(calc)
                if calc.inventory:
                    idx = input("Enter item index to remove: ").strip()
                    try:
                        calc.remove_item(int(idx))
                        print("Item removed.")
                    except (ValueError, IndexError):
                        print("Invalid index.")
            elif choice == "7":
                confirm = input("Clear all inventory? [y/N]: ").strip().lower()
                if confirm == 'y':
                    calc.clear_inventory()
                    print("Inventory cleared.")
            elif choice == "8":
                print("Goodbye!")
                break
            else:
                print("Invalid option.")


if __name__ == "__main__":
    main()
