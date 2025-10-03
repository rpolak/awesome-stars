#!/usr/bin/env python3
"""
Quick test script to analyze a small subset of repositories
"""

import re
from analyze_staleness import GitHubAnalyzer

def extract_sample_repos(readme_path: str, limit: int = 20) -> list:
    """Extract a small sample of repos for testing"""
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = r'https://github\.com/([^/\s\)]+)/([^/\s\)]+)'
    matches = re.findall(pattern, content)
    
    repos = []
    for owner, repo in matches[:limit]:
        repo = re.sub(r'[^\w\-\.].*$', '', repo)
        repos.append(f"{owner}/{repo}")
    
    return list(set(repos))

def main():
    print("Running test analysis on sample repositories...")
    analyzer = GitHubAnalyzer()
    
    # Get a small sample
    repos = extract_sample_repos('README.md', 10)
    print(f"Testing with {len(repos)} repositories:")
    
    stale_repos = []
    active_repos = []
    
    for i, repo in enumerate(repos, 1):
        print(f"[{i}/{len(repos)}] Analyzing {repo}...")
        repo_info = analyzer.get_repo_info(repo)
        staleness = analyzer.analyze_staleness(repo_info)
        
        repo_result = {
            'repo': repo,
            'staleness_score': staleness['staleness_score'],
            'category': staleness['category'],
            'reasons': staleness['reasons']
        }
        
        if staleness['is_stale']:
            stale_repos.append(repo_result)
        else:
            active_repos.append(repo_result)
        
        print(f"  Score: {staleness['staleness_score']}, Category: {staleness['category']}")
        if staleness['reasons']:
            print(f"  Reasons: {', '.join(staleness['reasons'])}")
    
    print(f"\n{'='*60}")
    print("TEST RESULTS")
    print(f"{'='*60}")
    print(f"Stale repositories: {len(stale_repos)}")
    print(f"Active repositories: {len(active_repos)}")
    
    if stale_repos:
        print(f"\nSTALE REPOSITORIES:")
        for repo in sorted(stale_repos, key=lambda x: x['staleness_score'], reverse=True):
            print(f"• {repo['repo']} (Score: {repo['staleness_score']})")
            print(f"  {', '.join(repo['reasons'])}")
    
    print(f"\nTest completed successfully! The full analysis should work.")

if __name__ == '__main__':
    main()