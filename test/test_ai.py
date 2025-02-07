import google.generativeai as genai
from starlib.starAI import *

def get_weather(location: str, unit: str = 'celsius'):
    """取得指定地點的即時天氣資訊"""
    # 實際應接入氣象API
    return {"temperature": 28, "condition": "晴"} 

def set_light_values(brightness:int, color_temp:str):
    """Set the brightness and color temperature of a room light. (mock API).

    Args:
        brightness: Light level from 0 to 100. Zero is off and 100 is full brightness
        color_temp: Color temperature of the light fixture, which can be `daylight`, `cool` or `warm`.

    Returns:
        A dictionary containing the set brightness and color temperature.
    """
    return {
        "brightness": brightness,
        "colorTemperature": color_temp
    }

def power_disco_ball(power: bool) -> bool:
    """Powers the spinning disco ball."""
    print(f"Disco ball is {'spinning!' if power else 'stopped.'}")
    return power


def start_music(energetic: bool, loud: bool, bpm: int) -> str:
    """Play some music matching the specified parameters.

    Args:
      energetic: Whether the music is energetic or not.
      loud: Whether the music is loud or not.
      bpm: The beats per minute of the music.

    Returns: The name of the song being played.
    """
    print(f"Starting music! {energetic=} {loud=}, {bpm=}")
    return "Never gonna give you up."


def dim_lights(brightness: float) -> bool:
    """Dim the lights.

    Args:
      brightness: The brightness of the lights, 0.0 is off, 1.0 is full.
    """
    print(f"Lights are now set to {brightness:.0%}")
    return True

generation_config = genai.GenerationConfig(
    temperature=0.3,
    max_output_tokens=2048,
    top_p=0.95
)
tool_config = {
    "function_calling_config": {
    "mode": "AUTO"
  }
}

tools = [get_weather, set_light_values, power_disco_ball, start_music]
function_map = {fn.__name__: fn for fn in tools}

model = genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config,tools=tools, tool_config=tool_config)

# Call the API.
chat = model.start_chat()
response = chat.send_message("Turn this place into a party!")

# Print out each of the function calls requested from this single call.
function_results = {}

for part in response.parts:
    if fn := part.function_call:
        args = ", ".join(f"{key}={val}" for key, val in fn.args.items())
        print(f"{fn.name}({args})")
        function_results[fn.name] = function_map[fn.name](**fn.args)

print(function_results)

# Build the response parts.
response_parts = [
    genai.protos.Part(function_response=genai.protos.FunctionResponse(name=fn, response={"result": val}))
    for fn, val in function_results.items()
]

response_new = chat.send_message(response_parts)
print(response_new.text)
print(len(chat.history))