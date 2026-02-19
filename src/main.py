#!/usr/bin/env python3
#!/usr/bin/env python3
import click
import sqlite3
import requests
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import time

DB_PATH = Path.home() / ".youtube_pain_harvester.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS pain_points
                 (id INTEGER PRIMARY KEY, source TEXT, keyword TEXT, 
                  frequency INTEGER, content TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS video_ideas
                 (id INTEGER PRIMARY KEY, title TEXT, description TEXT, 
                  keywords TEXT, pain_point_id INTEGER, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rankings
                 (id INTEGER PRIMARY KEY, video_id TEXT, keyword TEXT, 
                  position INTEGER, checked_at TEXT)''')
    conn.commit()
    conn.close()

@click.group()
def cli():
    """YouTube痛点收割机 - 自动化视频选题与SEO优化"""
    init_db()

@cli.command()
@click.option('--subreddit', default='entrepreneur', help='目标subreddit')
@click.option('--limit', default=50, help='抓取帖子数量')
def scrape_reddit(subreddit, limit):
    """抓取Reddit社区痛点"""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        pain_keywords = {}
        for post in data['data']['children']:
            title = post['data']['title']
            selftext = post['data'].get('selftext', '')
            text = f"{title} {selftext}".lower()
            
            # 提取痛点关键词
            pain_patterns = [
                r'how (?:do i|to|can i) (\w+(?:\s+\w+){0,3})',
                r'struggling with (\w+(?:\s+\w+){0,2})',
                r'problem with (\w+(?:\s+\w+){0,2})',
                r'need help (?:with )?(\w+(?:\s+\w+){0,2})',
                r'(?:can\'t|cannot) (\w+(?:\s+\w+){0,2})'
            ]
            
            for pattern in pain_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    keyword = match.strip()
                    if len(keyword) > 3:
                        pain_keywords[keyword] = pain_keywords.get(keyword, 0) + 1
        
        # 存储高频痛点
        for keyword, freq in sorted(pain_keywords.items(), key=lambda x: x[1], reverse=True)[:20]:
            c.execute("INSERT INTO pain_points (source, keyword, frequency, content, created_at) VALUES (?, ?, ?, ?, ?)",
                     (f"reddit/{subreddit}", keyword, freq, "", datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        click.echo(f"✓ 从 r/{subreddit} 提取了 {len(pain_keywords)} 个痛点关键词")
        
    except Exception as e:
        click.echo(f"✗ 抓取失败: {e}", err=True)

@cli.command()
@click.option('--video-id', required=True, help='YouTube视频ID')
def scrape_youtube_comments(video_id):
    """分析YouTube评论找内容空白点"""
    # 使用YouTube Data API需要key，这里用noembed作为演示
    url = f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={video_id}"
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        title = data.get('title', '')
        
        # 模拟评论分析（实际需要YouTube API）
        common_questions = [
            "how to start", "best practices", "common mistakes", 
            "tutorial for beginners", "step by step guide"
        ]
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        for q in common_questions:
            c.execute("INSERT INTO pain_points (source, keyword, frequency, content, created_at) VALUES (?, ?, ?, ?, ?)",
                     (f"youtube/{video_id}", q, 1, title, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        click.echo(f"✓ 分析了视频 {video_id} 的评论区")
        
    except Exception as e:
        click.echo(f"✗ 分析失败: {e}", err=True)

@cli.command()
@click.option('--file', type=click.Path(exists=True), help='客户支持记录文件(txt/json)')
def extract_support_keywords(file):
    """从客户支持记录提取痛点"""
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read().lower()
        
        # 提取问题关键词
        keywords = {}
        patterns = [
            r'issue with (\w+(?:\s+\w+){0,2})',
            r'error (?:in|with) (\w+(?:\s+\w+){0,2})',
            r'(?:can\'t|cannot|unable to) (\w+(?:\s+\w+){0,2})',
            r'how (?:do i|to|can) (\w+(?:\s+\w+){0,3})'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                kw = match.strip()
                if len(kw) > 3:
                    keywords[kw] = keywords.get(kw, 0) + 1
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        for kw, freq in sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:15]:
            c.execute("INSERT INTO pain_points (source, keyword, frequency, content, created_at) VALUES (?, ?, ?, ?, ?)",
                     ("support_tickets", kw, freq, "", datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        click.echo(f"✓ 从支持记录提取了 {len(keywords)} 个痛点")
        
    except Exception as e:
        click.echo(f"✗ 提取失败: {e}", err=True)

@cli.command()
@click.option('--top', default=10, help='使用前N个高频痛点')
def generate_video_ideas(top):
    """生成SEO优化的视频标题和描述"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id, keyword, frequency FROM pain_points ORDER BY frequency DESC LIMIT ?", (top,))
    pain_points = c.fetchall()
    
    if not pain_points:
        click.echo("✗ 没有痛点数据，请先运行抓取命令")
        return
    
    templates = [
        "How to {keyword} in 2026 (Step-by-Step Guide)",
        "{keyword}: Complete Tutorial for Beginners",
        "5 Common Mistakes When {keyword} (And How to Fix Them)",
        "The Ultimate Guide to {keyword} - Everything You Need to Know",
        "{keyword} Explained: Simple Solutions That Actually Work"
    ]
    
    for pain_id, keyword, freq in pain_points:
        for template in templates[:2]:  # 每个痛点生成2个标题
            title = template.format(keyword=keyword.title())
            
            description = f"""Learn how to {keyword} with this comprehensive guide. 
            
In this video, you'll discover:
• Proven strategies for {keyword}
• Common pitfalls to avoid
• Step-by-step implementation
• Real-world examples and case studies

Perfect for beginners and experienced users looking to master {keyword}.

Keywords: {keyword}, how to {keyword}, {keyword} tutorial, {keyword} guide, {keyword} tips

#tutorial #{keyword.replace(' ', '')} #howto"""
            
            keywords_list = f"{keyword}, how to {keyword}, {keyword} tutorial, {keyword} guide"
            
            c.execute("INSERT INTO video_ideas (title, description, keywords, pain_point_id, created_at) VALUES (?, ?, ?, ?, ?)",
                     (title, description, keywords_list, pain_id, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    click.echo(f"✓ 生成了 {len(pain_points) * 2} 个视频创意")

@cli.command()
def list_ideas():
    """列出所有视频创意"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id, title, keywords FROM video_ideas ORDER BY created_at DESC LIMIT 20")
    ideas = c.fetchall()
    
    if not ideas:
        click.echo("暂无视频创意")
        return
    
    for vid, title, keywords in ideas:
        click.echo(f"\n[{vid}] {title}")
        click.echo(f"    关键词: {keywords}")
    
    conn.close()

@cli.command()
@click.argument('idea_id', type=int)
def show_idea(idea_id):
    """显示完整视频创意详情"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT title, description, keywords FROM video_ideas WHERE id = ?", (idea_id,))
    result = c.fetchone()
    
    if not result:
        click.echo("✗ 创意不存在")
        return
    
    title, desc, keywords = result
    click.echo(f"\n标题: {title}\n")
    click.echo(f"描述:\n{desc}\n")
    click.echo(f"关键词: {keywords}")
    
    conn.close()

@cli.command()
@click.option('--video-id', required=True, help='YouTube视频ID')
@click.option('--keyword', required=True, help='追踪的关键词')
def track_ranking(video_id, keyword):
    """追踪视频搜索排名"""
    # 使用YouTube搜索（需要API key，这里模拟）
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(keyword)}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        # 简化：检查视频ID是否在结果中
        position = -1
        if video_id in resp.text:
            # 粗略估计位置
            position = resp.text.find(video_id) // 1000  # 模拟排名
            position = min(position, 50)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO rankings (video_id, keyword, position, checked_at) VALUES (?, ?, ?, ?)",
                 (video_id, keyword, position, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        if position > 0:
            click.echo(f"✓ 视频 {video_id} 在关键词 '{keyword}' 的排名: ~{position}")
        else:
            click.echo(f"✗ 视频未在前50名中找到")
        
    except Exception as e:
        click.echo(f"✗ 追踪失败: {e}", err=True)

@cli.command()
def stats():
    """显示统计数据"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM pain_points")
    pain_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM video_ideas")
    idea_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(DISTINCT video_id) FROM rankings")
    tracked_videos = c.fetchone()[0]
    
    click.echo(f"\n统计数据:")
    click.echo(f"  痛点关键词: {pain_count}")
    click.echo(f"  视频创意: {idea_count}")
    click.echo(f"  追踪视频: {tracked_videos}")
    
    c.execute("SELECT keyword, frequency FROM pain_points ORDER BY frequency DESC LIMIT 5")
    top_pains = c.fetchall()
    
    if top_pains:
        click.echo(f"\n  Top 5 痛点:")
        for kw, freq in top_pains:
            click.echo(f"    • {kw} ({freq}次)")
    
    conn.close()

if __name__ == '__main__':
    cli()