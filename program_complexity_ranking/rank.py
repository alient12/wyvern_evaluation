import json
import os
import csv

def compute_project_metrics(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)

    total_complexity = sum(entry.get("Complexity", 0) for entry in data)
    total_code = sum(entry.get("Code", 0) for entry in data)

    return total_complexity, total_code


def load_projects(directory):
    projects = []

    for file in os.listdir(directory):
        if file.endswith(".json"):
            path = os.path.join(directory, file)
            complexity, code = compute_project_metrics(path)

            projects.append({
                "project": file.replace(".json", ""),
                "complexity": complexity,
                "code": code,
                "complexity_per_loc": complexity / code if code > 0 else 0
            })

    return projects


def save_csv(filename, data):
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "rank", "project", "complexity", "code", "complexity_per_loc"
        ])
        writer.writeheader()
        writer.writerows(data)


def print_table(title, data):
    print(f"\n=== {title} ===")
    print(f"{'Rank':<5} {'Project':<20} {'Complexity':<12} {'LOC':<10} {'Comp/LOC':<10}")
    print("-" * 65)

    for row in data:
        print(f"{row['rank']:<5} {row['project']:<20} {row['complexity']:<12} {row['code']:<10} {row['complexity_per_loc']:.6f}")


if __name__ == "__main__":
    directory = "./"  # <-- change this

    projects = load_projects(directory)

    # Ranking 1: Total Complexity
    by_total = sorted(projects, key=lambda x: x["complexity"], reverse=True)
    for i, p in enumerate(by_total, 1):
        p["rank"] = i

    # Ranking 2: Complexity per LOC
    by_density = sorted(projects, key=lambda x: x["complexity_per_loc"], reverse=True)
    for i, p in enumerate(by_density, 1):
        p["rank"] = i

    # Print both
    print_table("Ranking by Total Complexity", by_total)
    print_table("Ranking by Complexity per LOC", by_density)

    # Save outputs
    save_csv("ranking_total_complexity.csv", by_total)
    save_csv("ranking_complexity_density.csv", by_density)

    print("\nSaved:")
    print("- ranking_total_complexity.csv")
    print("- ranking_complexity_density.csv")