How to use MCP tools with a PydanticAI Agent | by Finn Andersen | Medium

Sitemap

Open in app

Sign in

Write

Sign in

# How to use MCP tools with a PydanticAI Agent

Finn Andersen

6 min read

·

Mar 13, 2025

--

Guess how this was made

EDIT: MCP support has now been added to PydanticAI, but this article is still useful for seeing how it all works under the hood!

The Model Context Protocol (MCP) enables connecting AI Agents to tools and resources, however it’s currently not natively supported by the PydanticAI framework. Here I’ll demonstrate how to overcome this limitation so you can build powerful AI Agents! (Spoiler: it’s not pretty). It should also provide insight into how to use an MCP server with other agent frameworks, or without any at all.

# What is MCP?

The Model Context Protocol (MCP) is an initiative introduced by Anthropic to define a standardized way in which AI Agents can be connected to external context, such as resources to provide information or tools to take actions. The general idea is to have a MCP server which provides a set of tools or resources, and an MCP client which can connect to one or more servers to access their functionality and provide it to an AI Agent.

This aims to remove the coupling between services that provide context or tools, and the AI frameworks or models that need to access them. Read more about it here!

# PydanticAI

> PydanticAI is a Python agent framework designed to make it less painful to build production grade applications with Generative AI.

It’s a framework that’s generally more intuitive and flexible for developing AI agents than cumbersome alternatives like LangChain. Check out my article comparing the two here.

However, it doesn’t natively support MCP yet, so it’s not so straightforward to create an AI agent that can take advantage of all the cool functionality delivered via the protocol. I decided to take this opportunity to deep-dive into MCP and figure out how to integrate it “from scratch”!

# Preparing a MCP Server

I wanted to focus on connecting a PydanticAI Agent with an existing MCP server implementation, instead of creating my own (since that’s the whole point of the protocol!). Luckily there is a repository of reference implementations of basic MCP servers providing access to services like Slack, Google Drive, Github and various databases. To keep things simple and boring, I decided to use the Filesystem server to help create an agent that could assist with software development by being able to read and edit files.

It’s implemented as a simple Node package/tool which can be run locally and communicates over STDIO:

```
npx -y @modelcontextprotocol/server-filesystem "/path/to/working/dir"
```

After some testing I soon discovered that the file search and directory tree tools had some issues and were impractical to use with code repositories since they became overwhelmed with content within node\_modules or a Python virtual environment, or other files that would normally be ignored by Git or your IDE. Therefore I made a copy of the server implementation and added some custom enhancements to make relevant tools respect any .gitignore rules, so their outputs are much more usable. (I also opened a PR to fix the behaviour of the search\_files tool).

# Providing the tools to PydanticAI Agent

The next challenge is how to register the capabilities that the MCP server provides as tools to a PydanticAI Agent. Using the MCP Python SDK to start a MCP server, connect to it with a client and see what tools it provides looks like:

```


from mcp import ClientSession, StdioServerParameters from mcp.client.stdio import stdio_client



# Define server configuration server_params = StdioServerParameters( command="npx", args=[ "tsx", "server/index.ts", "path/to/working/directory", ], )



# Start server and connect client async with stdio_client(server_params) as (read, write): async with ClientSession(read, write) as session: # Initialize the connection await session.initialize()



# Get details of available tools tools_result = await session.list_tools() tools = tools_result.tools


```

Here, tools is a list of Tool Pydantic models which define the name, description and input schema of each available tool, in basically the same format as most LLM APIs require tool specifications to be provided. However, unfortunately PydanticAI does not currently support providing the input schema of a function tool directly; it can only construct it by inspecting a function signature.

Therefore, in order to work around this limitation, I needed to build the capability to convert an MCP Tool specification into a dynamic function definition, just so that PydanticAI can convert it back into a JSON tool specification again :’). At a high level, it works like this:

```


async def get_tools(session: ClientSession) -> list[Tool[AgentDeps]]: """ Get all tools from the MCP session and convert them to Pydantic AI tools. """ tools_result = await session.list_tools() 

return [pydantic_tool_from_mcp_tool(session, tool) for tool in tools_result.tools]



def pydantic_tool_from_mcp_tool(session: ClientSession, tool: MCPTool) -> Tool[AgentDeps]: """ Convert a MCP tool to a Pydantic AI tool. """ tool_function = create_function_from_schema(session=session, name=tool.name, schema=tool.inputSchema) return Tool(name=tool.name, description=tool.description, function=tool_function, takes_ctx=True)


```

For the implementation of create\_function\_from\_schema(), the key part is that we need to define a function for each tool that makes an actual request to the MCP server, which will perform the actual action and then return a response. This looks like:

```


def create_function_from_schema(session: ClientSession, name: str, schema: Dict[str, Any]) -> types.FunctionType: """ Create a function with a signature based on a JSON schema. This is necessary because PydanticAI does not yet support providing a tool JSON schema directly. """ # Create parameter list from tool schema parameters = convert_schema_to_params(schema)



# Create the signature sig = inspect.Signature(parameters=parameters)



# Create function body async def function_body(ctx: RunContext[AgentDeps], **kwargs) -> str: # Call the MCP tool with provided arguments result = await session.call_tool(name, arguments=kwargs)



# Assume response is always TextContent if isinstance(result.content[0], TextContent): return result.content[0].text else: raise ValueError("Expected TextContent, got ", type(result.content[0]))



# Create the function with the correct signature dynamic_function = types.FunctionType( function_body.__code__, function_body.__globals__, name=name, argdefs=function_body.__defaults__, closure=function_body.__closure__, )



# Add signature and annotations dynamic_function.__signature__ = sig # type: ignore dynamic_function.__annotations__ = {param.name: param.annotation for param in parameters}



return dynamic_function


```

For those who are brave or masochistic enough to want to see what convert\_schema\_to\_params() actually involves, then take a look here. Thankfully I got Claude/Cursor to do that dirty work for me... I can only pray that the crew at PydanticAI merges this PR soon so that no-one else has to be exposed to that abomination.

# Putting it all together

Now that we’ve got a list of standard PydanticAI Tools , they can be provided directly to an an Agent which can be used as normal, for example:

```


from pydantic_ai import Agent from rich.console import Console from rich.prompt import Prompt ...



def run(): # Configure Model and Agent dependencies ... # Initialise & connect MCP server, construct tools ...



agent = Agent( model=model, deps_type=type(deps), system_prompt=SYSTEM_PROMPT, tools=tools, )



message_history: list[ModelMessage] = [] while True: prompt = Prompt.ask("[cyan]>[/cyan] ").strip()



if not prompt: continue



# Handle special commands if prompt.lower() in EXIT_COMMANDS: break



# Process normal input through the agent result = await agent.run(prompt, deps=deps, message_history=message_history) response = result.data



console.print(f"[bold green]Agent:[/bold green] {response}") message_history = result.all_messages()


```

To explore my full implementation, check out the repository here. Have a go at using the Filesystem Agent yourself to see what it can do! Here’s an example:

```


Welcome to MCP Demo CLI! Type /quit to exit.



[DEBUG] Starting MCP server with working directory: /Users/finn.andersen/projects/mcp_demo [DEBUG] Secure MCP Filesystem Server running on stdio [DEBUG] Allowed directories: [ '/Users/finn.andersen/projects/mcp_demo' ]



> : Create a file that contains a directory tree structure of the project in a hierarchical format which shows depth of each item using indentation, using a similar format as the result of the "tree" tool. Exclude hidden files and folders



[DEBUG] Calling tool directory_tree with arguments: {'path': '.'} [DEBUG] Calling tool write_file with arguments: {'path': 'directory_tree.txt', 'content': '...'}



Agent: The directory tree has been successfully written to a file named `directory_tree.txt`. If you need anything else, feel free to ask! > :


```

It successfully created a file directory\_tree.txt with contents:

```
Makefile README.md client __init__.py mcp_agent __init__.py agent.py cli.py deps.py llm.py run.py tools.py util __init__.py schema_to_params.py pyproject.toml requirements-dev.txt requirements.txt server Dockerfile README.md index.ts package-lock.json package.json test.ts tsconfig.json uv.lock
```

# Wrapping Up

I hope this helps with understanding how MCP works, and how it can be used to integrate AI Agents with new functionality. Go build something cool with all the MCP servers freely available!

AI

Llm

Model Context Protocol

Pydantic Ai

--

--

## Written by Finn Andersen

221 followers

·22 following

Tech projects and other things on my mind

## Responses (3)

Help

Status

About

Care

Press

Blog

Privacy

Rules

Terms

Text to speech