"""Read MCP capability metadata; never executes a market query or prints keys."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
os.environ['JUNFEI_ACCOUNT_DATA'] = str(Path.home() / 'AmazonListingWorkbenchData')
sys.path.insert(0, str(ROOT / 'listing-workbench'))
import sellersprite

client = sellersprite.Client().connect()
names = sorted(client.tools)
tools = [tool for name, tool in client.tools.items()
         if any(word in name.lower() for word in ('seller', 'store', 'listing', 'product_research'))]
result = {'purpose': 'capability_metadata_only', 'marketQueriesExecuted': 0,
          'toolNames': names, 'discoveryToolMetadata': tools}
output = ROOT / 'automation/data/sellersprite-discovery-metadata-20261102.json'
with output.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print(json.dumps({'toolNames': names, 'discoveryToolMetadata': tools}, ensure_ascii=False))
