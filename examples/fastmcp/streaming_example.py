"""
Example of using streaming partial results with FastMCP.

This demonstrates how to:
1. Implement a tool that streams partial results
2. Use the stream=True option in client.call_tool()
"""

import asyncio

from mcp.server.fastmcp import Context, FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent


def create_streaming_server() -> FastMCP:
    """Create a FastMCP server with streaming tools."""
    mcp = FastMCP(name="StreamingExampleServer")

    @mcp.tool(description="A tool that streams partial results")
    async def streaming_counter(count: int, delay: float, ctx: Context) -> str:
        """Stream counting results with specified delay between updates.

        Args:
            count: Number of items to process
            delay: Delay in seconds between updates
        """
        for i in range(1, count + 1):
            # Stream a partial result
            # This sends a response with hasMore=True in _meta
            await ctx.stream_partial([TextContent(type="text", text=f"Processing item {i}/{count}")])

            # Simulate work with delay
            await asyncio.sleep(delay)

        # Return the final result (hasMore=False or no hasMore in _meta)
        return f"Completed processing {count} items"

    @mcp.tool(description="A regular non-streaming tool")
    async def normal_tool(message: str) -> str:
        """Just returns the message as-is."""
        return message

    return mcp


async def demo_streaming():
    """Demonstrate streaming functionality."""
    mcp = create_streaming_server()

    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        await session.initialize()

        # Example 1: Use as AsyncGenerator
        print("STREAMING EXAMPLE (AsyncGenerator):")
        print("----------------------------------")

        # Get the async generator using the dedicated streaming method
        print("Streaming results from streaming_counter tool...")
        tool_call_stream = session.stream_tool("streaming_counter", {"count": 5, "delay": 1})

        # Iterate through partial results
        print("Starting to iterate through streaming results...")
        count = 0
        async for partial_result in tool_call_stream:
            count += 1
            print(f"Received result {count}:")
            if partial_result and partial_result.content:
                print(f"  Content: {partial_result.content[0].text}")
            # print(f"  hasMore: {partial_result.has_more}")

        print(f"Received a total of {count} results")

        # Example 2: Regular tool call (no streaming)
        print("\nREGULAR EXAMPLE (No streaming):")
        print("------------------------------")
        result = await session.call_tool("streaming_counter", {"count": 5, "delay": 1})
        print(f"Result: {result.content[0].text if result.content else 'No content'}")


if __name__ == "__main__":
    asyncio.run(demo_streaming())
