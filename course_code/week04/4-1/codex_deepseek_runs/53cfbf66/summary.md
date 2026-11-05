**任务交接摘要**

目标：修复 `session.py` 中会话在到期瞬间仍有效的问题。
限制：不得修改测试。
真实失败：`test_at` 断言 `is_active(100,100)` 为 False，实际返回 True；测试 3 项 1 失败。
当前版本：`2b2bcb44`；日志 `test-f4296ecf.log`（位于 `.../53cfbf66/`）。
未做：尚未修改代码，也未重新运行测试。
下一步：将 `now <= expires_at` 改为 `now < expires_at` 后运行测试。