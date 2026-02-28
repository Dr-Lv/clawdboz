#!/usr/bin/env python3
"""
Local Memory Management - 本地记忆管理
支持保存、检索、管理记忆，提供关键词搜索和语义相似度匹配
"""

import os
import json
import sqlite3
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class Memory:
    """记忆条目"""
    id: str
    content: str
    category: str
    tags: List[str]
    importance: int  # 1-5，5为最重要
    created_at: str
    updated_at: str
    access_count: int = 0
    last_accessed: Optional[str] = None


class MemoryManager:
    """本地记忆管理器"""
    
    def __init__(self, storage_dir: Optional[str] = None):
        """初始化记忆管理器
        
        Args:
            storage_dir: 存储目录，默认 ~/.local/share/local-memory/
        """
        if storage_dir is None:
            storage_dir = os.path.expanduser("~/.local/share/local-memory")
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.storage_dir / "memories.db"
        self.embeddings_dir = self.storage_dir / "embeddings"
        self.embeddings_dir.mkdir(exist_ok=True)
        
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    tags TEXT DEFAULT '[]',
                    importance INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON memories(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON memories(created_at)")
            conn.commit()
    
    def _generate_id(self, content: str) -> str:
        """生成记忆ID"""
        timestamp = datetime.now().isoformat()
        return hashlib.md5(f"{content}{timestamp}".encode()).hexdigest()[:12]
    
    def save(self, content: str, category: str = "general", 
             tags: Optional[List[str]] = None, importance: int = 3) -> str:
        """保存记忆
        
        Args:
            content: 记忆内容
            category: 分类，默认 general
            tags: 标签列表
            importance: 重要程度 1-5
            
        Returns:
            memory_id: 记忆ID
        """
        if tags is None:
            tags = []
        
        memory_id = self._generate_id(content)
        now = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO memories 
                (id, content, category, tags, importance, created_at, updated_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                memory_id, content, category, 
                json.dumps(tags, ensure_ascii=False),
                importance, now, now
            ))
            conn.commit()
        
        # 保存语义向量（简化实现：基于关键词的哈希）
        self._save_embedding(memory_id, content)
        
        return memory_id
    
    def _save_embedding(self, memory_id: str, content: str):
        """保存语义向量（简化版：关键词频率）"""
        # 提取关键词（简化处理）
        words = re.findall(r'\w+', content.lower())
        word_freq = {}
        for word in words:
            if len(word) > 1:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        embedding_path = self.embeddings_dir / f"{memory_id}.json"
        with open(embedding_path, 'w', encoding='utf-8') as f:
            json.dump(word_freq, f, ensure_ascii=False)
    
    def _compute_similarity(self, query_words: Dict[str, int], memory_id: str) -> float:
        """计算语义相似度"""
        embedding_path = self.embeddings_dir / f"{memory_id}.json"
        if not embedding_path.exists():
            return 0.0
        
        with open(embedding_path, 'r', encoding='utf-8') as f:
            memory_words = json.load(f)
        
        # 计算余弦相似度（简化版）
        common_words = set(query_words.keys()) & set(memory_words.keys())
        if not common_words:
            return 0.0
        
        dot_product = sum(query_words[w] * memory_words[w] for w in common_words)
        query_norm = sum(v**2 for v in query_words.values()) ** 0.5
        memory_norm = sum(v**2 for v in memory_words.values()) ** 0.5
        
        if query_norm == 0 or memory_norm == 0:
            return 0.0
        
        return dot_product / (query_norm * memory_norm)
    
    def search(self, keyword: str, category: Optional[str] = None) -> List[Dict]:
        """关键词搜索
        
        Args:
            keyword: 搜索关键词
            category: 可选的分类过滤
            
        Returns:
            匹配的记忆列表
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if category:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE category = ? AND content LIKE ? ORDER BY created_at DESC",
                    (category, f"%{keyword}%")
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE content LIKE ? ORDER BY created_at DESC",
                    (f"%{keyword}%",)
                )
            
            rows = cursor.fetchall()
        
        results = []
        for row in rows:
            memory = dict(row)
            memory['tags'] = json.loads(memory['tags'])
            results.append(memory)
            
            # 更新访问计数
            self._update_access_count(memory['id'])
        
        return results
    
    def search_similar(self, query: str, top_k: int = 5) -> List[Dict]:
        """语义相似度搜索
        
        Args:
            query: 查询内容
            top_k: 返回结果数量
            
        Returns:
            最相关的记忆列表
        """
        # 构建查询向量
        words = re.findall(r'\w+', query.lower())
        query_words = {}
        for word in words:
            if len(word) > 1:
                query_words[word] = query_words.get(word, 0) + 1
        
        # 获取所有记忆
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM memories")
            all_memories = [dict(row) for row in cursor.fetchall()]
        
        # 计算相似度
        similarities = []
        for memory in all_memories:
            sim = self._compute_similarity(query_words, memory['id'])
            similarities.append((memory, sim))
        
        # 排序并返回 top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        results = []
        for memory, sim in similarities[:top_k]:
            if sim > 0:  # 只返回有相似度的
                memory['tags'] = json.loads(memory['tags'])
                memory['similarity'] = round(sim, 4)
                results.append(memory)
                self._update_access_count(memory['id'])
        
        return results
    
    def _update_access_count(self, memory_id: str):
        """更新访问计数"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (now, memory_id)
            )
            conn.commit()
    
    def get(self, memory_id: str) -> Optional[Dict]:
        """获取单个记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            记忆内容，不存在返回 None
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
        
        if row:
            memory = dict(row)
            memory['tags'] = json.loads(memory['tags'])
            self._update_access_count(memory_id)
            return memory
        return None
    
    def delete(self, memory_id: str) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            是否删除成功
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
        
        # 删除嵌入向量
        embedding_path = self.embeddings_dir / f"{memory_id}.json"
        if embedding_path.exists():
            embedding_path.unlink()
        
        return cursor.rowcount > 0
    
    def update(self, memory_id: str, **kwargs) -> bool:
        """更新记忆
        
        Args:
            memory_id: 记忆ID
            **kwargs: 要更新的字段
            
        Returns:
            是否更新成功
        """
        allowed_fields = {'content', 'category', 'tags', 'importance'}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        if 'tags' in updates:
            updates['tags'] = json.dumps(updates['tags'], ensure_ascii=False)
        
        updates['updated_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [memory_id]
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE memories SET {set_clause} WHERE id = ?",
                values
            )
            conn.commit()
        
        # 如果内容更新，重新计算嵌入
        if 'content' in updates:
            self._save_embedding(memory_id, kwargs['content'])
        
        return cursor.rowcount > 0
    
    def list_all(self, category: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """列出所有记忆
        
        Args:
            category: 可选的分类过滤
            limit: 返回数量限制
            
        Returns:
            记忆列表
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if category:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                    (category, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            
            rows = cursor.fetchall()
        
        results = []
        for row in rows:
            memory = dict(row)
            memory['tags'] = json.loads(memory['tags'])
            results.append(memory)
        
        return results
    
    def cleanup(self, days: int = 30) -> int:
        """清理旧记忆
        
        Args:
            days: 删除多少天前的记忆
            
        Returns:
            删除的记忆数量
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            # 获取要删除的ID
            cursor = conn.execute(
                "SELECT id FROM memories WHERE created_at < ?",
                (cutoff_date,)
            )
            ids_to_delete = [row[0] for row in cursor.fetchall()]
            
            # 删除记录
            cursor = conn.execute("DELETE FROM memories WHERE created_at < ?", (cutoff_date,))
            deleted_count = cursor.rowcount
            conn.commit()
        
        # 删除对应的嵌入文件
        for memory_id in ids_to_delete:
            embedding_path = self.embeddings_dir / f"{memory_id}.json"
            if embedding_path.exists():
                embedding_path.unlink()
        
        return deleted_count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆库统计信息
        
        Returns:
            统计信息字典
        """
        with sqlite3.connect(self.db_path) as conn:
            # 总数量
            cursor = conn.execute("SELECT COUNT(*) FROM memories")
            total = cursor.fetchone()[0]
            
            # 分类统计
            cursor = conn.execute(
                "SELECT category, COUNT(*) FROM memories GROUP BY category"
            )
            by_category = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 最近添加
            cursor = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE created_at > ?",
                ((datetime.now() - timedelta(days=7)).isoformat(),)
            )
            recent = cursor.fetchone()[0]
            
            # 最常访问
            cursor = conn.execute(
                "SELECT id, content, access_count FROM memories ORDER BY access_count DESC LIMIT 5"
            )
            most_accessed = [
                {'id': row[0], 'content': row[1][:50] + '...', 'access_count': row[2]}
                for row in cursor.fetchall()
            ]
        
        return {
            'total_memories': total,
            'by_category': by_category,
            'recent_7_days': recent,
            'most_accessed': most_accessed,
            'storage_dir': str(self.storage_dir)
        }
    
    def export(self, output_path: str):
        """导出所有记忆到 JSON 文件
        
        Args:
            output_path: 输出文件路径
        """
        memories = self.list_all(limit=10000)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
    
    def import_from(self, input_path: str):
        """从 JSON 文件导入记忆
        
        Args:
            input_path: 输入文件路径
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            memories = json.load(f)
        
        for memory in memories:
            self.save(
                content=memory['content'],
                category=memory.get('category', 'general'),
                tags=memory.get('tags', []),
                importance=memory.get('importance', 3)
            )


# CLI 接口
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Local Memory Management")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # save
    save_parser = subparsers.add_parser('save', help='Save a memory')
    save_parser.add_argument('content', help='Memory content')
    save_parser.add_argument('--category', '-c', default='general', help='Category')
    save_parser.add_argument('--tags', '-t', default='', help='Tags (comma-separated)')
    save_parser.add_argument('--importance', '-i', type=int, default=3, help='Importance (1-5)')
    
    # search
    search_parser = subparsers.add_parser('search', help='Search memories by keyword')
    search_parser.add_argument('keyword', help='Search keyword')
    search_parser.add_argument('--category', '-c', help='Filter by category')
    
    # similar
    similar_parser = subparsers.add_parser('similar', help='Semantic search')
    similar_parser.add_argument('query', help='Query text')
    similar_parser.add_argument('--top-k', '-k', type=int, default=5, help='Number of results')
    
    # list
    list_parser = subparsers.add_parser('list', help='List all memories')
    list_parser.add_argument('--category', '-c', help='Filter by category')
    list_parser.add_argument('--limit', '-l', type=int, default=20, help='Limit')
    
    # delete
    delete_parser = subparsers.add_parser('delete', help='Delete a memory')
    delete_parser.add_argument('memory_id', help='Memory ID')
    
    # cleanup
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old memories')
    cleanup_parser.add_argument('--days', '-d', type=int, default=30, help='Days to keep')
    
    # stats
    stats_parser = subparsers.add_parser('stats', help='Show statistics')
    
    # export
    export_parser = subparsers.add_parser('export', help='Export memories')
    export_parser.add_argument('--output', '-o', default='memories.json', help='Output file')
    
    # import
    import_parser = subparsers.add_parser('import', help='Import memories')
    import_parser.add_argument('--input', '-i', required=True, help='Input file')
    
    args = parser.parse_args()
    
    memory = MemoryManager()
    
    if args.command == 'save':
        tags = [t.strip() for t in args.tags.split(',') if t.strip()]
        mid = memory.save(args.content, args.category, tags, args.importance)
        print(f"✅ Saved with ID: {mid}")
    
    elif args.command == 'search':
        results = memory.search(args.keyword, args.category)
        print(f"🔍 Found {len(results)} results:")
        for r in results:
            print(f"  [{r['id'][:8]}] {r['content'][:60]}... ({r['category']})")
    
    elif args.command == 'similar':
        results = memory.search_similar(args.query, args.top_k)
        print(f"🔍 Found {len(results)} similar memories:")
        for r in results:
            sim_pct = r.get('similarity', 0) * 100
            print(f"  [{r['id'][:8]}] ({sim_pct:.1f}%) {r['content'][:50]}...")
    
    elif args.command == 'list':
        results = memory.list_all(args.category, args.limit)
        print(f"📋 {len(results)} memories:")
        for r in results:
            print(f"  [{r['id'][:8]}] [{r['category']}] {r['content'][:50]}...")
    
    elif args.command == 'delete':
        if memory.delete(args.memory_id):
            print(f"✅ Deleted {args.memory_id}")
        else:
            print(f"❌ Not found: {args.memory_id}")
    
    elif args.command == 'cleanup':
        count = memory.cleanup(args.days)
        print(f"🧹 Cleaned up {count} old memories")
    
    elif args.command == 'stats':
        stats = memory.get_stats()
        print(f"📊 Memory Statistics:")
        print(f"  Total: {stats['total_memories']}")
        print(f"  Recent (7 days): {stats['recent_7_days']}")
        print(f"  By category: {stats['by_category']}")
        print(f"  Storage: {stats['storage_dir']}")
    
    elif args.command == 'export':
        memory.export(args.output)
        print(f"✅ Exported to {args.output}")
    
    elif args.command == 'import':
        memory.import_from(args.input)
        print(f"✅ Imported from {args.input}")
    
    else:
        parser.print_help()
