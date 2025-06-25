"""
Test the tool streaming feature using stdio transport.
"""

import asyncio
import pytest
from mcp.server.fastmcp import Context, FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent


def create_streaming_server() -> FastMCP:
    mcp = FastMCP(name="StreamingTestServer")

    @mcp.tool(description="A tool that streams partial results")
    async def streaming_counter(count: int, delay: float, ctx: Context) -> str:
        for i in range(1, count + 1):
            await ctx.stream_partial([TextContent(type="text", text=f"Processing item {i}/{count}")])
            await asyncio.sleep(delay)
        return f"Completed processing {count} items"

    @mcp.tool(description="A non-streaming tool for testing")
    async def regular_tool(message: str) -> str:
        return message

    return mcp


@pytest.mark.anyio
async def test_streaming_tool_basic():
    mcp = create_streaming_server()
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        await session.initialize()
        tool_call_stream = session.stream_tool("streaming_counter", {"count": 3, "delay": 0.01})
        results = [r async for r in tool_call_stream]
        assert len(results) == 4
        for i, result in enumerate(results):
            assert len(result.content) == 1
            assert isinstance(result.content[0], TextContent)
            text_content = result.content[0]
            if i < len(results) - 1:
                # Check hasMore in _meta for partial results
                assert result.meta is not None
                assert result.meta.get("hasMore") is True
                assert text_content.text.startswith("Processing item")
            else:
                # Final result should not have hasMore=True (can be None, False, or omitted)
                has_more = result.meta and result.meta.get("hasMore", False) if result.meta else False
                assert has_more is False
                assert text_content.text == "Completed processing 3 items"


@pytest.mark.anyio
async def test_streaming_tool_direct_iteration():
    mcp = create_streaming_server()
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        await session.initialize()
        tool_call_stream = session.stream_tool("streaming_counter", {"count": 5, "delay": 0.01})
        expected_texts = [
            "Processing item 1/5",
            "Processing item 2/5",
            "Processing item 3/5",
            "Processing item 4/5",
            "Processing item 5/5",
            "Completed processing 5 items",
        ]
        count = 0
        async for result in tool_call_stream:
            assert isinstance(result, CallToolResult)
            assert len(result.content) == 1
            assert isinstance(result.content[0], TextContent)
            content_block = result.content[0]
            assert content_block.text == expected_texts[count]
            expected_is_partial = count < len(expected_texts) - 1
            # Check hasMore in _meta
            has_more = result.meta and result.meta.get("hasMore", False) if result.meta else False
            assert has_more is expected_is_partial
            count += 1
        assert count == len(expected_texts)


@pytest.mark.anyio
async def test_streaming_tool_multiple_concurrent():
    mcp = create_streaming_server()
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        await session.initialize()
        stream1 = session.stream_tool("streaming_counter", {"count": 3, "delay": 0.01})
        stream2 = session.stream_tool("streaming_counter", {"count": 2, "delay": 0.01})
        results1 = []
        results2 = []

        async def collect_stream1():
            async for result in stream1:
                results1.append(result)

        async def collect_stream2():
            async for result in stream2:
                results2.append(result)

        await asyncio.gather(collect_stream1(), collect_stream2())
        assert len(results1) == 4
        assert results1[-1].content[0].text == "Completed processing 3 items"
        # Final result should not have hasMore=True (can be None, False, or omitted)
        has_more_1 = results1[-1].meta and results1[-1].meta.get("hasMore", False) if results1[-1].meta else False
        assert has_more_1 is False
        assert len(results2) == 3
        assert results2[-1].content[0].text == "Completed processing 2 items"
        has_more_2 = results2[-1].meta and results2[-1].meta.get("hasMore", False) if results2[-1].meta else False
        assert has_more_2 is False


@pytest.mark.anyio
async def test_regular_tool_compatibility():
    mcp = create_streaming_server()
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        await session.initialize()
        result = await session.call_tool("regular_tool", {"message": "Hello, world!"})
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == "Hello, world!"
        # Regular tool result should not have hasMore=True (can be None, False, or omitted)
        has_more = result.meta and result.meta.get("hasMore", False) if result.meta else False
        assert has_more is False


@pytest.mark.anyio
async def test_streaming_early_exit():
    mcp = create_streaming_server()
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        await session.initialize()
        tool_call_stream = session.stream_tool("streaming_counter", {"count": 10, "delay": 0.01})
        count = 0
        async for result in tool_call_stream:
            count += 1
            # Check hasMore in _meta
            expected_has_more = count < 11  # All but the last should have hasMore=true
            has_more = result.meta and result.meta.get("hasMore", False) if result.meta else False
            assert has_more is expected_has_more
            if count == 3:
                break
        assert count == 3
        result = await session.call_tool("regular_tool", {"message": "Still working"})
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == "Still working"


@pytest.mark.anyio
async def test_call_tool_with_streaming_server():
    """Test that call_tool works correctly with tools that use streaming."""
    mcp = create_streaming_server()
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        await session.initialize()

        # call_tool should return only the final result, even with streaming tools
        result = await session.call_tool("streaming_counter", {"count": 5, "delay": 0.01})
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)

        # Should get the final result, not a partial
        content_block = result.content[0]
        assert content_block.text == "Completed processing 5 items"

        # Final result should not have hasMore=True
        has_more = result.meta and result.meta.get("hasMore", False) if result.meta else False
        assert has_more is False

        # call_tool should also work with regular non-streaming tools
        result2 = await session.call_tool("regular_tool", {"message": "test message"})
        assert isinstance(result2, CallToolResult)
        assert len(result2.content) == 1
        assert isinstance(result2.content[0], TextContent)
        assert result2.content[0].text == "test message"
