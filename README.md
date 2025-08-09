# MealMD

A simple, interactive terminal bot that walks you through a few quick questions and recommends meal ideas tailored to your goals, tastes, and dietary restrictions — all offline.

## Features
- Step-by-step interactive wizard — answer simple numbered questions
- Filters meals based on your preferences and avoidances
- Scores and recommends the top matches
- Shows ingredients, macros, sodium, and notes for each meal
- Runs entirely in your terminal (no internet connection required)

## Prerequisites
Python 3.8+ is required. Install it if you don’t already have it.

**Linux (Debian/Ubuntu)**
```bash
sudo apt update
sudo apt install python3 -y
```

**macOS (with Homebrew)**
```bash
brew install python
```

**Windows**
```powershell
# Download from: https://www.python.org/downloads/
# During installation, check "Add Python to PATH".
```

## Installation
Clone this repository:
```bash
git clone https://github.com/imightbeparker/MealMD.git
cd MealMD
```

## Usage
Run the wizard:
```bash
python3 mealmd_wizard.py
```
Follow the prompts, and MealMD will recommend the best meal options for you.
