#!/usr/bin/env python3
"""MealMD — step-by-step terminal bot that suggests meals.

Features:
- Guided “wizard” flow with Back support
- Clean prompts with ANSI colors (disable via --no-color)
- Centralized scoring weights (easy to tweak)
- Deterministic tie-breaking via --seed
- JSON output with --json (good for piping/automation)
- Remembers your last answers in ~/.mealmdrc (press Enter to accept defaults)
- NEW: Multi-select avoidances in one step (e.g., 1,4,7)

No external dependencies. Python 3.8+.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import argparse
import json
import os
import random
import sys

# ---------------- UI Helpers ---------------- #

class C:
    """ANSI colors (can be disabled)."""
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"

def enable_color(enable: bool) -> None:
    if not enable:
        for k, v in C.__dict__.items():
            if isinstance(v, str) and v.startswith("\033"):
                setattr(C, k, "")

def ask(
    prompt: str,
    choices: List[str],
    allow_zero: bool = False,
    allow_back: bool = False,
    default_index: Optional[int] = None,
) -> int:
    """Return 1..len(choices); 0 if allow_zero; -1 if 'b' and allow_back; Enter => default."""
    print(f"\n{C.BOLD}{prompt}{C.RESET}")
    for i, ch in enumerate(choices, start=1):
        print(f"{i}. {ch}")
    if allow_zero:
        print("0. None/Done")
    if allow_back:
        print("b. Back")

    while True:
        sel = input("> ").strip().lower()
        if default_index is not None and sel == "":
            return default_index
        if allow_back and sel == "b":
            return -1
        if allow_zero and sel == "0":
            return 0
        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(choices):
                return idx
        print(f"{C.YELLOW}Please enter a valid option.{C.RESET}")

def ask_multi(
    prompt: str,
    choices: List[str],
    allow_back: bool = False,
    preselected: Optional[List[int]] = None,
) -> List[int]:
    """Multi-select by comma: returns sorted list of indices (1-based). Empty list = none."""
    print(f"\n{C.BOLD}{prompt}{C.RESET}")
    for i, ch in enumerate(choices, start=1):
        print(f"{i}. {ch}")
    print("0. None/Done")  # <-- Added explicit None option
    if allow_back:
        print("b. Back")
    if preselected:
        labels = ", ".join(choices[i-1] for i in sorted(set(preselected)) if 1 <= i <= len(choices))
        print(f"{C.DIM}(Preselected: {labels}){C.RESET}")
    print(f"{C.DIM}Enter numbers separated by commas (e.g., 1,4,6) or 0 for none.{C.RESET}")

    while True:
        raw = input("> ").strip().lower()
        if allow_back and raw == "b":
            return [-1]  # sentinel for "back"
        if raw == "0":
            return []
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if all(p.isdigit() for p in parts):
            idxs = [int(p) for p in parts]
            if all(1 <= i <= len(choices) for i in idxs):
                return sorted(set(idxs))  # dedupe + sort
        print(f"{C.YELLOW}Please enter valid numbers like 1,3,7 (or 0 for none).{C.RESET}")

# ---------------- Data ---------------- #

@dataclass
class Meal:
    name: str
    items: List[str]
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    sodium_mg: int
    calcium_mg: int
    protein_type: str       # 'beef','poultry','fish','shellfish','plant'
    allergens: List[str]    # ['dairy','gluten','nuts','eggs','soy','shellfish','sesame']
    effort: str             # 'low','med','high'
    takeout_ok: bool
    spice: str              # 'mild','medium','spicy'
    notes: List[str] = field(default_factory=list)

MEALS: List[Meal] = [
    Meal("Grilled Salmon Bowl",
         ["grilled salmon 5 oz","quinoa 1 cup","spinach","tomato","olive oil","lemon","plain yogurt 1/2 cup"],
         650,45,55,24,520,250,"fish",["dairy"],"med",True,"mild",["Omega-3s"]),
    Meal("Chicken Thigh + Sweet Potato Plate",
         ["roasted chicken thigh 6 oz","baked sweet potato","steamed broccoli","tahini drizzle"],
         620,42,62,18,480,180,"poultry",["sesame"],"med",True,"mild",["balanced"]),
    Meal("Tofu Stir-Fry",
         ["extra-firm tofu 6 oz","mixed vegetables","brown rice 1 cup","garlic-ginger sauce (low sodium)"],
         600,36,70,16,420,350,"plant",["soy","gluten?"],"low",False,"medium",["plant protein"]),
    Meal("Lentil Curry + Rice",
         ["red lentil curry 1.5 cups","basmati rice 1 cup","cucumber salad"],
         680,32,98,16,540,140,"plant",[],"med",True,"medium",["good fiber"]),
    Meal("Turkey Chili (Lean)",
         ["ground turkey 93% 6 oz","beans","tomato","onion","spices"],
         640,48,58,18,620,160,"poultry",[],"med",True,"medium",["high protein"]),
    Meal("Beef Steak Plate",
         ["sirloin steak 6 oz","roasted potatoes","asparagus","butter"],
         720,50,46,30,540,60,"beef",["dairy?"],"high",True,"mild",["creatine-rich"]),
    Meal("Egg White Veggie Omelet + Oats",
         ["egg white omelet (4 whites)","mixed veggies","rolled oats 1 cup","berries"],
         520,36,66,8,420,180,"plant",["eggs","gluten?"],"low",False,"mild",["light"]),
    Meal("Greek Yogurt Power Bowl",
         ["plain Greek yogurt 1.5 cups","berries","chia seeds","walnuts","honey"],
         580,42,48,20,180,450,"plant",["dairy","nuts"],"low",False,"mild",["easy"]),
    Meal("Sardine Avocado Toast",
         ["whole-grain toast 2 slices","sardines in olive oil 1 tin","avocado","lemon"],
         560,32,44,28,520,320,"fish",["gluten?","fish"],"low",True,"mild",["omega-3s"]),
    Meal("Tempeh Buddha Bowl",
         ["tempeh 6 oz","farro 1 cup","kale","roasted peppers","tahini-lemon"],
         620,38,70,16,460,220,"plant",["soy","sesame"],"med",False,"mild",["fermented"]),
    Meal("Shrimp Rice Bowl",
         ["shrimp 6 oz","jasmine rice 1 cup","cabbage slaw","lime","olive oil"],
         600,42,64,14,640,160,"shellfish",["shellfish"],"low",True,"mild",["lean protein"]),
    Meal("Chickpea Pasta Primavera",
         ["chickpea pasta 3 oz dry","zucchini","tomato","olive oil","basil"],
         580,34,70,14,380,120,"plant",[],"low",False,"mild",["high fiber"]),
]

# Centralized weights so tuning is transparent
WEIGHTS: Dict[str, int] = {
    "match_protein_pref": 8,
    "mismatch_protein_pref": 4,
    "plant_only_penalty": 30,
    "fish_pref_bonus": 6,

    "goal_cut": 10,
    "goal_bulk": 10,
    "goal_maint": 5,

    "fat_penalty_cut": 4,

    "pre_low_fat": 6,
    "pre_good_carbs": 4,
    "pre_mod_protein": 3,

    "post_protein": 6,
    "post_carbs": 4,
    "post_low_fat": 2,

    "effort_low_bonus": 6,
    "effort_low_penalty": 3,
    "effort_med_bonus": 3,
    "effort_high_bonus": 4,
    "effort_restaurant_bonus": 5,
    "effort_restaurant_penalty": 4,

    "sodium_low_bonus": 5,
    "sodium_high_penalty": 6,
    "sodium_too_high_penalty": 2,

    "spice_match_bonus": 2,
}

# ---------------- Core logic ---------------- #

def score_meal(meal: Meal, ans: Dict[str, Any]):
    score = 50.0
    reasons: List[str] = []
    flags: List[str] = []

    goal = ans["goal"]              # cut/maintenance/bulk
    timing = ans["timing"]          # pre/post/any
    protein_pref = ans["protein_pref"]
    avoids = set(ans["avoids"])
    effort = ans["effort"]
    sodium_pref = ans["sodium_pref"]
    spice_pref = ans["spice_pref"]

    # Avoidances filter
    if any(a in meal.allergens for a in avoids):
        return -999, ["conflicts with avoidances"], ["contains allergen"]

    # Protein preference
    if protein_pref == "no-preference":
        pass
    elif protein_pref == "plant-only":
        if meal.protein_type != "plant":
            score -= WEIGHTS["plant_only_penalty"]; reasons.append("prefers plant-only")
    elif protein_pref == "fish/seafood":
        if meal.protein_type not in ("fish","shellfish"):
            score -= WEIGHTS["mismatch_protein_pref"]
        else:
            score += WEIGHTS["fish_pref_bonus"]; reasons.append("matches fish/seafood preference")
    else:
        if meal.protein_type == protein_pref:
            score += WEIGHTS["match_protein_pref"]; reasons.append("matches protein preference")
        else:
            score -= WEIGHTS["mismatch_protein_pref"]

    # Goals
    if goal == "cut":
        if meal.calories <= 600 and meal.protein_g >= 35:
            score += WEIGHTS["goal_cut"]; reasons.append("cut: high protein, moderate calories")
        if meal.fat_g > 22:
            score -= WEIGHTS["fat_penalty_cut"]
    elif goal == "bulk":
        if meal.calories >= 650 and meal.protein_g >= 40:
            score += WEIGHTS["goal_bulk"]; reasons.append("bulk: higher cals & protein")
        elif meal.calories < 600:
            score -= 3
    else:  # maintenance
        if 500 <= meal.calories <= 700:
            score += WEIGHTS["goal_maint"]; reasons.append("maintenance-friendly calories")

    # Timing
    if timing == "pre":
        if meal.fat_g <= 20: score += WEIGHTS["pre_low_fat"]; reasons.append("pre: lighter fat")
        else: score -= WEIGHTS["pre_low_fat"]
        if 40 <= meal.carbs_g <= 90: score += WEIGHTS["pre_good_carbs"]; reasons.append("pre: good carbs")
        if 25 <= meal.protein_g <= 40: score += WEIGHTS["pre_mod_protein"]
    elif timing == "post":
        if meal.protein_g >= 35: score += WEIGHTS["post_protein"]; reasons.append("post: protein for recovery")
        if meal.carbs_g >= 50: score += WEIGHTS["post_carbs"]
        if meal.fat_g <= 20: score += WEIGHTS["post_low_fat"]

    # Effort
    if effort == "low":
        if meal.effort == "low": score += WEIGHTS["effort_low_bonus"]; reasons.append("low effort prep")
        else: score -= WEIGHTS["effort_low_penalty"]
    elif effort == "med":
        if meal.effort in ("low","med"): score += WEIGHTS["effort_med_bonus"]
    elif effort == "high":
        if meal.effort == "high": score += WEIGHTS["effort_high_bonus"]
        else: score -= 2
    elif effort == "restaurant":
        if meal.takeout_ok: score += WEIGHTS["effort_restaurant_bonus"]; reasons.append("restaurant/takeout friendly")
        else: score -= WEIGHTS["effort_restaurant_penalty"]

    # Sodium
    if sodium_pref == "lower":
        if meal.sodium_mg <= 500: score += WEIGHTS["sodium_low_bonus"]; reasons.append("lower sodium")
        elif meal.sodium_mg > 700: score -= WEIGHTS["sodium_high_penalty"]
    else:
        if meal.sodium_mg > 850: score -= WEIGHTS["sodium_too_high_penalty"]

    # Spice
    if spice_pref != "no-pref" and meal.spice == spice_pref:
        score += WEIGHTS["spice_match_bonus"]

    # Flags for optional ingredients
    if "gluten?" in meal.allergens: flags.append("gluten depends on ingredients")
    if "dairy?"  in meal.allergens: flags.append("omit butter to be dairy-free")

    return score, reasons, flags

def recommend(ans: Dict[str, Any], top_k: int = 3, seed: Optional[int] = None) -> Dict[str, Any]:
    scored = []
    for m in MEALS:
        s, r, f = score_meal(m, ans)
        if s > -500:
            scored.append((s, m, r, f))

    if not scored:
        return {
            "top_recommendations": [],
            "explanation": "No meals fit all choices. Try relaxing one avoidance or picking 'No preference'."
        }

    if seed is not None:
        random.seed(seed)
        random.shuffle(scored)

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]
    out = []
    for s, m, r, f in top:
        out.append({
            "name": m.name,
            "items": m.items,
            "macros": {"calories": m.calories, "protein_g": m.protein_g, "carbs_g": m.carbs_g, "fat_g": m.fat_g},
            "sodium_mg": m.sodium_mg,
            "score": round(s, 1),
            "reasons": r,
            "flags": f
        })
    return {"top_recommendations": out, "explanation": "Simple terminal helper for meal ideas."}

# ---------------- Prefs ---------------- #

RC_PATH = os.path.expanduser("~/.mealmdrc")

def load_prefs() -> Optional[Dict[str, Any]]:
    try:
        if os.path.exists(RC_PATH):
            with open(RC_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return None

def save_prefs(ans: Dict[str, Any]) -> None:
    try:
        with open(RC_PATH, "w", encoding="utf-8") as f:
            json.dump(ans, f, indent=2)
    except OSError:
        pass

# ---------------- CLI ---------------- #

def parse_args():
    p = argparse.ArgumentParser(description="MealMD — step-by-step meal recommender.")
    p.add_argument("--json", action="store_true", help="Print recommendations as JSON and exit.")
    p.add_argument("--seed", type=int, help="Seed for deterministic tie-breaking.")
    p.add_argument("--top", type=int, default=3, help="How many meals to show (default: 3).")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    p.add_argument("--no-save", action="store_true", help="Don't save your answers to ~/.mealmdrc.")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    enable_color(not args.no_color)

    print(f"{C.BOLD}=== MealMD (step-by-step) ==={C.RESET}")
    print("Answer with the number of your choice. Type 'b' to go back when available.")

    # Pre-init for static analysis (values set by wizard)
    goal: Optional[str] = None
    timing: Optional[str] = None
    protein_pref: Optional[str] = None
    effort: Optional[str] = None
    sodium_pref: Optional[str] = None
    spice_pref: Optional[str] = None
    avoids: List[str] = []

    prior = load_prefs() or {}

    # 1) Goal
    goal_default = {"cut":1, "maintenance":2, "bulk":3}.get(prior.get("goal"))
    g = ask("What's your current goal?", ["Cut (lean)", "Maintenance", "Bulk (gain)"], default_index=goal_default)
    goal = {1:"cut", 2:"maintenance", 3:"bulk"}[g]

    # 2) Timing
    while True:
        timing_default = {"pre":1, "post":2, "any":3}.get(prior.get("timing"))
        t = ask("When is this meal?", ["Pre-workout (0–2h before)", "Post-workout (0–2h after)", "Anytime"],
                allow_back=True, default_index=timing_default)
        if t == -1:
            # back to goal
            g = ask("What's your current goal?", ["Cut (lean)", "Maintenance", "Bulk (gain)"], default_index=goal_default)
            goal = {1:"cut", 2:"maintenance", 3:"bulk"}[g]
            continue
        timing = {1:"pre", 2:"post", 3:"any"}[t]
        break

    # 3) Protein preference
    while True:
        prot_default = {"beef":1,"poultry":2,"fish/seafood":3,"plant-only":4,"no-preference":5}.get(prior.get("protein_pref"))
        p = ask("Pick a protein preference.", ["Beef/red meat", "Poultry (chicken/turkey)", "Fish/seafood", "Plant-only", "No preference"],
                allow_back=True, default_index=prot_default)
        if p == -1:
            # back to timing
            continue
        protein_pref = {1:"beef", 2:"poultry", 3:"fish/seafood", 4:"plant-only", 5:"no-preference"}[p]
        break

    # 4) Avoidances (multi-select in one go)
    avoids_lookup = ["Dairy","Gluten","Nuts","Eggs","Soy","Shellfish","Sesame"]
    pre_idxs = [avoids_lookup.index(a.capitalize()) + 1 for a in prior.get("avoids", []) if a.capitalize() in avoids_lookup]
    while True:
        idxs = ask_multi(
            "Do you need to avoid anything? (comma-separated, Enter for none).",
            avoids_lookup + [],  # copy for safety
            allow_back=True,
            preselected=pre_idxs if pre_idxs else None,
        )
        if idxs == [-1]:
            # back to protein pref
            prot_default = {"beef":1,"poultry":2,"fish/seafood":3,"plant-only":4,"no-preference":5}.get(prior.get("protein_pref"))
            p = ask("Pick a protein preference.", ["Beef/red meat", "Poultry (chicken/turkey)", "Fish/seafood", "Plant-only", "No preference"],
                    default_index=prot_default)
            protein_pref = {1:"beef", 2:"poultry", 3:"fish/seafood", 4:"plant-only", 5:"no-preference"}[p]
            continue
        avoids = [avoids_lookup[i-1].lower() for i in idxs]  # store as lowercase keys
        if avoids:
            print(f"{C.CYAN}Avoiding: {', '.join(avoids)}{C.RESET}")
        break

    # 5) Effort
    while True:
        effort_default = {"low":1, "med":2, "high":3, "restaurant":4}.get(prior.get("effort"))
        e = ask("How much cooking effort?", ["Low (<15 min)", "Medium (15–30 min)", "High (>30 min)", "Restaurant/Takeout OK"],
                allow_back=True, default_index=effort_default)
        if e == -1:
            # back to avoids
            continue
        effort = {1:"low", 2:"med", 3:"high", 4:"restaurant"}[e]
        break

    # 6) Sodium
    while True:
        sodium_default = {"normal":1, "lower":2}.get(prior.get("sodium_pref"))
        s = ask("Sodium needs?", ["Normal", "Lower sodium"], allow_back=True, default_index=sodium_default)
        if s == -1:
            # back to effort
            continue
        sodium_pref = {1:"normal", 2:"lower"}[s]
        break

    # 7) Spice
    while True:
        spice_default = {"mild":1, "medium":2, "spicy":3, "no-pref":4}.get(prior.get("spice_pref"))
        sp = ask("Spice preference?", ["Mild", "Medium", "Spicy", "No preference"], allow_back=True, default_index=spice_default)
        if sp == -1:
            # back to sodium
            continue
        spice_pref = {1:"mild", 2:"medium", 3:"spicy", 4:"no-pref"}[sp]
        break

    answers = {
        "goal": goal,
        "timing": timing,
        "protein_pref": protein_pref,
        "avoids": avoids,
        "effort": effort,
        "sodium_pref": sodium_pref,
        "spice_pref": spice_pref,
    }

    if not args.no_save:
        save_prefs(answers)

    results = recommend(answers, top_k=args.top, seed=args.seed)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"\n{C.BOLD}=== Top Picks ==={C.RESET}")
    if not results["top_recommendations"]:
        print(results["explanation"])
        sys.exit(0)

    for i, r in enumerate(results["top_recommendations"], start=1):
        print(f"\n{C.CYAN}{i}) {r['name']}{C.RESET}  (score: {r['score']})")
        print("   Items: " + ", ".join(r["items"]))
        m = r["macros"]
        print(f"   Macros: {m['calories']} kcal | P {m['protein_g']}g | C {m['carbs_g']}g | F {m['fat_g']}g")
        print(f"   Sodium: {r['sodium_mg']} mg")
        if r.get("flags"):
            print(f"   Flags: " + ", ".join(r["flags"]))
        print("   Why:")
        for why in r["reasons"]:
            print("    - " + why)

    print(f"\n{C.DIM}Just a simple helper for meal ideas — not medical advice.{C.RESET}")

if __name__ == "__main__":
    main()
