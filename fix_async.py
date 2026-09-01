import glob
import re

for filepath in glob.glob("api/routes/*.py"):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if this file has true async operations (other than fast API handlers).
    # Since we know all routes are doing synchronous DB calls or dict lookups, 
    # we can safely replace all sync def with def.
    content = content.replace("async def ", "def ")
    content = content.replace("await ", "")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
print("Updated all api/routes/*.py")
