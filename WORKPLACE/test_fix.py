#!/usr/bin/env python3
"""测试生成中字样移除逻辑"""

import sys
sys.path.insert(0, '/Users/suntom/work/test/larkbot')

# 模拟测试 is_completed 标志位和回调逻辑
def test_completion_logic():
    """测试完成标志位的逻辑"""
    is_completed = [False]
    last_content = [""]
    update_history = []
    
    def on_chunk(current_text):
        """模拟原始的 on_chunk"""
        if is_completed[0]:
            print(f"[on_chunk] 检测到 is_completed=True，跳过更新")
            return
        
        display_text = current_text + "\n\n◐ **生成中...**"
        update_history.append(("chunk", display_text))
        last_content[0] = current_text
        print(f"[on_chunk] 更新内容长度: {len(display_text)}, 包含'生成中': {'生成中' in display_text}")
    
    def on_chunk_final(final_text):
        """模拟最终的 on_chunk_final"""
        is_completed[0] = True
        update_history.append(("final", final_text))
        print(f"[on_chunk_final] 最终更新，长度: {len(final_text)}, 包含'生成中': {'生成中' in final_text}")
    
    # 模拟流式生成过程
    print("=== 模拟流式生成 ===")
    on_chunk("你好")
    on_chunk("你好，这是")
    on_chunk("你好，这是测试消息")
    
    # 模拟完成
    print("\n=== 模拟生成完成 ===")
    final_response = "你好，这是测试消息。生成完毕！"
    on_chunk_final(final_response)
    
    # 验证：再次调用 on_chunk 应该被阻止
    print("\n=== 验证 on_chunk 被阻止 ===")
    on_chunk("这是不应该出现的延迟更新")
    
    # 检查结果
    print("\n=== 更新历史 ===")
    for i, (update_type, text) in enumerate(update_history):
        has_generating = "生成中" in text
        print(f"[{i}] {update_type}: 长度={len(text)}, 包含'生成中'={has_generating}")
    
    # 验证最终状态
    final_updates = [u for u in update_history if u[0] == "final"]
    last_update = update_history[-1] if update_history else None
    
    print("\n=== 测试结果 ===")
    if final_updates and not any("生成中" in u[1] for u in final_updates):
        print("✅ 通过：最终更新不包含'生成中'字样")
    else:
        print("❌ 失败：最终更新仍包含'生成中'字样")
    
    if last_update and last_update[0] == "final":
        print("✅ 通过：最后一次更新是 final 类型")
    else:
        print("❌ 失败：最后一次更新不是 final 类型")

if __name__ == "__main__":
    test_completion_logic()
