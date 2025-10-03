#!/usr/bin/env python3
"""
Focused analysis script to identify the most likely stale repositories
from awesome-stars with optimized approach.
"""

import re
import json
from datetime import datetime
from analyze_staleness import GitHubAnalyzer
import time


def main():
    print("🔍 AWESOME STARS STALENESS ANALYSIS")
    print("=" * 50)

    analyzer = GitHubAnalyzer()

    # Extract all repositories
    print("📋 Extracting repositories from README...")
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"https://github\.com/([^/\s\)]+)/([^/\s\)]+)"
    matches = re.findall(pattern, content)

    repos = []
    for owner, repo in matches:
        repo = re.sub(r"[^\w\-\.].*$", "", repo)
        repos.append(f"{owner}/{repo}")

    repos = list(set(repos))  # Remove duplicates
    print(f"📊 Found {len(repos)} unique repositories")

    # Results storage
    results = {
        "analysis_date": datetime.now().isoformat(),
        "total_analyzed": 0,
        "stale_repos": [],
        "possibly_stale_repos": [],
        "archived_repos": [],
        "missing_repos": [],
        "error_count": 0,
    }

    print(f"\n🔬 Analyzing repositories (this may take a while)...")

    batch_size = 50  # Process in smaller batches
    for batch_start in range(0, len(repos), batch_size):
        batch_end = min(batch_start + batch_size, len(repos))
        batch_repos = repos[batch_start:batch_end]

        print(
            f"\n📦 Processing batch {batch_start//batch_size + 1}: repos {batch_start+1}-{batch_end}"
        )

        for i, repo in enumerate(batch_repos):
            progress = batch_start + i + 1
            print(f"[{progress:3d}/{len(repos)}] {repo:<40}", end=" ")

            try:
                repo_info = analyzer.get_repo_info(repo)

                if "error" in repo_info:
                    if repo_info.get("status_code") == 404:
                        results["missing_repos"].append(
                            {
                                "repo": repo,
                                "error": "Repository not found (deleted/moved)",
                            }
                        )
                        print("❌ NOT FOUND")
                    else:
                        results["error_count"] += 1
                        print(f"⚠️  ERROR: {repo_info['error']}")
                    continue

                # Quick staleness check
                staleness = analyzer.analyze_staleness(repo_info)
                results["total_analyzed"] += 1

                repo_result = {
                    "repo": repo,
                    "url": f"https://github.com/{repo}",
                    "description": repo_info.get("description", "")[:100],
                    "language": repo_info.get("language", "Unknown"),
                    "stars": repo_info.get("stargazers_count", 0),
                    "last_push": repo_info.get("pushed_at", ""),
                    "archived": repo_info.get("archived", False),
                    "fork": repo_info.get("fork", False),
                    "staleness_score": staleness["staleness_score"],
                    "reasons": staleness["reasons"],
                }

                if repo_info.get("archived", False):
                    results["archived_repos"].append(repo_result)
                    print("🗄️  ARCHIVED")
                elif staleness["staleness_score"] >= 50:
                    results["stale_repos"].append(repo_result)
                    print(f"🔴 STALE ({staleness['staleness_score']})")
                elif staleness["staleness_score"] >= 30:
                    results["possibly_stale_repos"].append(repo_result)
                    print(f"🟡 POSSIBLY STALE ({staleness['staleness_score']})")
                else:
                    print(f"✅ ACTIVE ({staleness['staleness_score']})")

                # Rate limiting
                time.sleep(0.05)  # Small delay to avoid rate limits

            except Exception as e:
                print(f"💥 EXCEPTION: {str(e)}")
                results["error_count"] += 1

        # Longer pause between batches
        if batch_end < len(repos):
            print(f"\n⏸️  Pausing 2 seconds between batches...")
            time.sleep(2)

    # Sort results
    results["stale_repos"].sort(key=lambda x: x["staleness_score"], reverse=True)
    results["possibly_stale_repos"].sort(
        key=lambda x: x["staleness_score"], reverse=True
    )
    results["archived_repos"].sort(key=lambda x: x["stars"], reverse=True)
    results["missing_repos"].sort(key=lambda x: x["repo"])

    # Save results
    output_file = f"staleness_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n💾 Results saved to: {output_file}")

    # Print summary
    print(f"\n{'='*80}")
    print("📈 ANALYSIS SUMMARY")
    print(f"{'='*80}")
    print(f"Total repositories found: {len(repos)}")
    print(f"Successfully analyzed: {results['total_analyzed']}")
    print(f"Archived repositories: {len(results['archived_repos'])}")
    print(f"Stale repositories: {len(results['stale_repos'])}")
    print(f"Possibly stale repositories: {len(results['possibly_stale_repos'])}")
    print(f"Missing/deleted repositories: {len(results['missing_repos'])}")
    print(f"Errors encountered: {results['error_count']}")

    # Show top stale repositories
    if results["stale_repos"]:
        print(f"\n🔴 TOP 10 STALE REPOSITORIES:")
        print("-" * 60)
        for repo in results["stale_repos"][:10]:
            print(f"• {repo['repo']} ⭐{repo['stars']}")
            print(f"  Score: {repo['staleness_score']} | {', '.join(repo['reasons'])}")
            if repo["description"]:
                print(f"  📝 {repo['description']}...")
            print()

    # Show archived repositories
    if results["archived_repos"]:
        print(f"\n🗄️  ARCHIVED REPOSITORIES ({len(results['archived_repos'])}):")
        print("-" * 60)
        for repo in results["archived_repos"][:10]:
            print(f"• {repo['repo']} ⭐{repo['stars']}")
            if repo["description"]:
                print(f"  📝 {repo['description']}...")
        if len(results["archived_repos"]) > 10:
            print(f"  ... and {len(results['archived_repos']) - 10} more")
        print()

    # Show missing repositories
    if results["missing_repos"]:
        print(f"\n❌ MISSING/DELETED REPOSITORIES ({len(results['missing_repos'])}):")
        print("-" * 60)
        for repo in results["missing_repos"]:
            print(f"• {repo['repo']}")
        print()

    # Show recommendations
    total_problematic = (
        len(results["stale_repos"])
        + len(results["archived_repos"])
        + len(results["missing_repos"])
    )
    if total_problematic > 0:
        percentage = (total_problematic / len(repos)) * 100
        print(f"💡 RECOMMENDATIONS:")
        print(
            f"   {total_problematic} repositories ({percentage:.1f}%) may need attention:"
        )
        print(
            f"   - Consider removing {len(results['missing_repos'])} missing repositories"
        )
        print(f"   - Review {len(results['archived_repos'])} archived repositories")
        print(f"   - Evaluate {len(results['stale_repos'])} stale repositories")
        print(
            f"   - Monitor {len(results['possibly_stale_repos'])} possibly stale repositories"
        )

    print(f"\n✅ Analysis complete! Check {output_file} for detailed results.")


if __name__ == "__main__":
    main()
