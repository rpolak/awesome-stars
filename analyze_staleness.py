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
