"""
黄金投资智能顾问 - 环境验证脚本
确认所有核心依赖能正常 import
"""
import sys

print("=" * 55)
print("  黄金投资智能顾问 - 环境验证")
print(f"  Python 版本: {sys.version.split()[0]}")
print(f"  Python 路径: {sys.executable}")
print("=" * 55)

results = []

def check(name, import_stmt, version_attr=None):
    try:
        mod = __import__(import_stmt, fromlist=["__version__"]) if version_attr else __import__(import_stmt)
        ver = getattr(mod, version_attr, None) if version_attr else None
        label = f"✅ ({ver})" if ver else "✅"
        results.append((name, label, None))
    except Exception as e:
        results.append((name, "❌", str(e)))

check("python-dotenv", "dotenv")
check("pandas", "pandas", "__version__")
check("numpy", "numpy", "__version__")
check("pandas-ta", "pandas_ta")
check("MetaTrader5", "MetaTrader5", "__version__")
check("requests", "requests")
check("beautifulsoup4", "bs4")
check("langchain", "langchain", "__version__")
check("langchain-openai", "langchain_openai")
check("langgraph", "langgraph")
check("streamlit", "streamlit", "__version__")
check("plotly", "plotly", "__version__")
check("Pillow", "PIL")

print("\n  检查结果:\n")
success_count = 0
for name, status, error in results:
    print(f"  {status}  {name:<22}", end="")
    if error:
        print(f" → {error}")
    else:
        print()
    if "✅" in status:
        success_count += 1

print(f"\n  总计: {success_count}/{len(results)} 通过")

if success_count == len(results):
    print("\n  🎉 所有依赖安装成功，可以启动项目！\n    streamlit run app.py\n")
else:
    print("\n  ⚠️  部分依赖安装失败，请运行: pip install -r requirements.txt\n")
print()
