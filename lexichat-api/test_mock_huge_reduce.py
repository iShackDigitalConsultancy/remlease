import asyncio
from services.map_reduce import reduce_phase

async def main():
    map_results = [{"doc": "test", "content": "test"}] * 1000
    res = await reduce_phase(map_results, "Extract expiries. JSON format required.")
    print(res)

asyncio.run(main())
