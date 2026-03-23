#!/usr/bin/env python3
"""
Analyze GitHub starred repositories to identify potentially stale projects.

This script checks various indicators of project staleness:
- Last commit date
- Last release date
- Issue activity
- Archive status
- Fork indicators
"""

import os
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
from urllib.parse import urlparse
import time


class GitHubAnalyzer:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update(
            {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "awesome-stars-analyzer",
            }
        )

    def extract_github_repos(self, readme_path: str) -> List[str]:
        """Extract GitHub repository URLs from README.md"""
        repos = []
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pattern to match GitHub URLs
        pattern = r"https://github\.com/([^/\s\)]+)/([^/\s\)]+)"
        matches = re.findall(pattern, content)

        for owner, repo in matches:
            # Clean up repo name (remove any trailing characters)
            repo = re.sub(r"[^\w\-\.].*$", "", repo)
            repos.append(f"{owner}/{repo}")

        return list(set(repos))  # Remove duplicates

    def get_repo_info(self, repo: str) -> Dict:
        """Get repository information from GitHub API"""
        try:
            response = self.session.get(f"https://api.github.com/repos/{repo}")
            if response.status_code == 404:
                return {"error": "Repository not found", "status_code": 404}
            elif response.status_code == 403:
                return {"error": "Rate limited or access denied", "status_code": 403}
            elif response.status_code != 200:
                return {
                    "error": f"HTTP {response.status_code}",
                    "status_code": response.status_code,
                }

            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def get_latest_release(self, repo: str) -> Optional[Dict]:
        """Get latest release information"""
        try:
            response = self.session.get(
                f"https://api.github.com/repos/{repo}/releases/latest"
            )
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None

    def analyze_staleness(self, repo_info: Dict) -> Dict:
        """Analyze various staleness indicators"""
        if "error" in repo_info:
            return {
                "staleness_score": 100,
                "reasons": [repo_info["error"]],
                "is_stale": True,
                "category": "error",
            }

        reasons = []
        staleness_score = 0

        # Check if archived
        if repo_info.get("archived", False):
            staleness_score += 50
            reasons.append("Repository is archived")

        # Check if it's just a fork without original development
        if repo_info.get("fork", False):
            staleness_score += 10
            reasons.append("Repository is a fork")

        # Check last push date
        pushed_at = repo_info.get("pushed_at")
        if pushed_at:
            pushed_date = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days_since_push = (datetime.now().astimezone() - pushed_date).days

            if days_since_push > 365 * 3:  # 3 years
                staleness_score += 40
                reasons.append(f"No commits in {days_since_push // 365} years")
            elif days_since_push > 365 * 2:  # 2 years
                staleness_score += 30
                reasons.append(f"No commits in {days_since_push // 365} years")
            elif days_since_push > 365:  # 1 year
                staleness_score += 20
                reasons.append(f"No commits in {days_since_push} days")
            elif days_since_push > 180:  # 6 months
                staleness_score += 10
                reasons.append(f"No commits in {days_since_push} days")

        # Check if repository has very few stars (might indicate lack of adoption)
        stars = repo_info.get("stargazers_count", 0)
        if stars < 10:
            staleness_score += 5
            reasons.append(f"Low adoption ({stars} stars)")

        # Check if repository has no recent releases
        # This would require another API call, so we'll skip for now to avoid rate limits

        # Determine staleness category
        if staleness_score >= 70:
            category = "very_stale"
        elif staleness_score >= 50:
            category = "stale"
        elif staleness_score >= 30:
            category = "possibly_stale"
        else:
            category = "active"

        return {
            "staleness_score": staleness_score,
            "reasons": reasons,
            "is_stale": staleness_score >= 50,
            "category": category,
            "last_push": pushed_at,
            "stars": stars,
            "archived": repo_info.get("archived", False),
            "fork": repo_info.get("fork", False),
        }

    def analyze_awesome_stars(self, readme_path: str, output_file: str = None) -> Dict:
        """Main analysis function"""
        print("Extracting repositories from README...")
        repos = self.extract_github_repos(readme_path)
        print(f"Found {len(repos)} unique repositories")

        results = {
            "analysis_date": datetime.now().isoformat(),
            "total_repos": len(repos),
            "stale_repos": [],
            "possibly_stale_repos": [],
            "active_repos": [],
            "error_repos": [],
        }

        print("\nAnalyzing repositories...")
        for i, repo in enumerate(repos, 1):
            print(f"[{i}/{len(repos)}] Analyzing {repo}...")

            repo_info = self.get_repo_info(repo)
            staleness = self.analyze_staleness(repo_info)

            repo_analysis = {
                "repo": repo,
                "url": f"https://github.com/{repo}",
                "staleness": staleness,
            }

            # Add additional info if available
            if "error" not in repo_info:
                repo_analysis.update(
                    {
                        "description": repo_info.get("description", ""),
                        "language": repo_info.get("language", "Unknown"),
                        "stars": repo_info.get("stargazers_count", 0),
                        "last_push": repo_info.get("pushed_at", ""),
                        "created_at": repo_info.get("created_at", ""),
                        "archived": repo_info.get("archived", False),
                    }
                )

            # Categorize
            if staleness["category"] == "error":
                results["error_repos"].append(repo_analysis)
            elif staleness["category"] in ["very_stale", "stale"]:
                results["stale_repos"].append(repo_analysis)
            elif staleness["category"] == "possibly_stale":
                results["possibly_stale_repos"].append(repo_analysis)
            else:
                results["active_repos"].append(repo_analysis)

            # Rate limiting - sleep between requests
            time.sleep(0.1)

        # Sort results by staleness score
        results["stale_repos"].sort(
            key=lambda x: x["staleness"]["staleness_score"], reverse=True
        )
        results["possibly_stale_repos"].sort(
            key=lambda x: x["staleness"]["staleness_score"], reverse=True
        )

        if output_file:
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to {output_file}")

        return results

    def print_summary(self, results: Dict):
        """Print a summary of the analysis"""
        print("\n" + "=" * 80)
        print("AWESOME STARS STALENESS ANALYSIS SUMMARY")
        print("=" * 80)

        print(f"Total repositories analyzed: {results['total_repos']}")
        print(f"Stale repositories: {len(results['stale_repos'])}")
        print(f"Possibly stale repositories: {len(results['possibly_stale_repos'])}")
        print(f"Active repositories: {len(results['active_repos'])}")
        print(f"Error repositories: {len(results['error_repos'])}")

        if results["stale_repos"]:
            print(f"\n🔴 TOP 10 STALE REPOSITORIES:")
            print("-" * 50)
            for repo in results["stale_repos"][:10]:
                reasons = ", ".join(repo["staleness"]["reasons"])
                print(
                    f"• {repo['repo']} (Score: {repo['staleness']['staleness_score']})"
                )
                print(f"  {reasons}")
                if repo.get("description"):
                    print(f"  Description: {repo['description'][:80]}...")
                print()

        if results["possibly_stale_repos"]:
            print(f"\n🟡 TOP 10 POSSIBLY STALE REPOSITORIES:")
            print("-" * 50)
            for repo in results["possibly_stale_repos"][:10]:
                reasons = ", ".join(repo["staleness"]["reasons"])
                print(
                    f"• {repo['repo']} (Score: {repo['staleness']['staleness_score']})"
                )
                print(f"  {reasons}")
                print()

        if results["error_repos"]:
            print(f"\n❌ REPOSITORIES WITH ERRORS:")
            print("-" * 50)
            for repo in results["error_repos"]:
                reasons = ", ".join(repo["staleness"]["reasons"])
                print(f"• {repo['repo']}: {reasons}")


def focused_analysis_mode(
    analyzer, readme_path: str, batch_size: int = 50
) -> Dict:
    """Focused analysis with batch processing and enhanced reporting"""
    print("🔍 AWESOME STARS STALENESS ANALYSIS (FOCUSED MODE)")
    print("=" * 50)

    # Extract all repositories
    print("📋 Extracting repositories from README...")
    with open(readme_path, "r", encoding="utf-8") as f:
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

    # Process in smaller batches
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

    return results


def print_focused_summary(results: Dict, output_file: str = None):
    """Print focused summary with recommendations"""
    repos_count = (
        len(results["stale_repos"])
        + len(results["possibly_stale_repos"])
        + len(results["archived_repos"])
        + len(results["missing_repos"])
    )

    print(f"\n{'='*80}")
    print("📈 ANALYSIS SUMMARY")
    print(f"{'='*80}")
    print(f"Total repositories found: {repos_count + results['total_analyzed']}")
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
        percentage = (total_problematic / results['total_analyzed']) * 100 if results['total_analyzed'] > 0 else 0
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

    if output_file:
        print(f"\n💾 Results saved to: {output_file}")
    print(f"\n✅ Analysis complete!")


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze awesome-stars for stale repositories"
    )
    parser.add_argument("--readme", default="README.md", help="Path to README.md file")
    parser.add_argument("--output", help="Output JSON file path")
    parser.add_argument(
        "--token", help="GitHub API token (or set GITHUB_TOKEN env var)"
    )
    parser.add_argument(
        "--mode",
        choices=["simple", "focused"],
        default="simple",
        help="Analysis mode: simple (basic summary) or focused (detailed with batch processing)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for focused mode (default: 50)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.readme):
        print(f"Error: README file not found: {args.readme}")
        return 1

    analyzer = GitHubAnalyzer(token=args.token)

    if not analyzer.token:
        print(
            "Warning: No GitHub token provided. Rate limits will be very restrictive."
        )
        print("Consider setting GITHUB_TOKEN environment variable or using --token")

    try:
        if args.mode == "focused":
            results = focused_analysis_mode(analyzer, args.readme, args.batch_size)
            if args.output:
                with open(args.output, "w") as f:
                    json.dump(results, f, indent=2)
            print_focused_summary(results, args.output)
        else:  # simple mode
            results = analyzer.analyze_awesome_stars(args.readme, args.output)
            analyzer.print_summary(results)
        return 0
    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user")
        return 1
    except Exception as e:
        print(f"Error during analysis: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
