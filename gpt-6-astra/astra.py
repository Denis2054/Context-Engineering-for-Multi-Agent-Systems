import base64
import io
import os
import time
from dotenv import load_dotenv
import pyautogui
from openai import OpenAI

load_dotenv()
client = OpenAI()

MODEL = "gpt-6-astra"

# Emergency stop:
# Move the mouse to the upper-left corner.
pyautogui.FAILSAFE = True

# Where screenshots will be saved.
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

screenshot_counter = 0


def screenshot_data_url():
    """
    Capture the current desktop, save it as a PNG,
    and return it as a data URL for Astra.
    """
    global screenshot_counter

    screenshot_counter += 1

    # Capture desktop.
    image = pyautogui.screenshot()

    # Save a local PNG copy.
    filename = f"screenshot_{screenshot_counter:03d}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)

    image.save(filepath, format="PNG")

    print()
    print("=" * 60)
    print(f"SCREENSHOT {screenshot_counter:03d}")
    print(f"Saved: {filepath}")
    print("=" * 60)

    # Also create the data URL for the API.
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    encoded = base64.b64encode(
        buffer.getvalue()
    ).decode()

    data_url = f"data:image/png;base64,{encoded}"

    return data_url


def execute_computer_action(action):
    """
    Translate an Astra computer action into a local
    PyAutoGUI operation.

    IMPORTANT:
    Keep this function deliberately restrictive.
    """

    action_type = action["type"]

    if action_type == "click":
        pyautogui.click(
            action["x"],
            action["y"],
            button=action.get("button", "left")
        )

    elif action_type == "double_click":
        pyautogui.doubleClick(
            action["x"],
            action["y"]
        )

    elif action_type == "move":
        pyautogui.moveTo(
            action["x"],
            action["y"]
        )

    elif action_type == "drag":
        pyautogui.moveTo(
            action["path"][0]["x"],
            action["path"][0]["y"]
        )

        for point in action["path"][1:]:
            pyautogui.moveTo(
                point["x"],
                point["y"],
                duration=0.05
            )

    elif action_type == "type":
        pyautogui.write(
            action["text"],
            interval=0.01
        )

    elif action_type == "keypress":
        keys = action.get("keys", [])

        if isinstance(keys, str):
            keys = [keys]

        # Handle key combinations such as CTRL+L.
        if len(keys) > 1:
            pyautogui.hotkey(*[
                key.lower()
                for key in keys
            ])
        elif len(keys) == 1:
            pyautogui.press(keys[0].lower())

    elif action_type == "scroll":
        amount = action.get(
            "scroll_y",
            action.get("amount", 0)
        )

        pyautogui.scroll(amount)

    elif action_type == "wait":
        time.sleep(
            action.get("duration", 1)
        )

    elif action_type == "screenshot":
        # The screenshot is taken automatically
        # after each action, so nothing needs to
        # be executed here.
        pass

    else:
        raise RuntimeError(
            f"Unsupported computer action: {action_type}"
        )


def confirm_action(action):
    """
    Human-in-the-loop safety gate.
    """

    print()
    print("Astra wants to perform:")
    print(action)

    answer = input("Allow this action? [y/N]: ")

    return answer.lower() == "y"


def describe_screenshot(screenshot):
    """
    Ask Astra to describe the current desktop screenshot.
    """

    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Look carefully at this desktop screenshot "
                            "and describe what you see. "
                            "Mention the main applications/windows, "
                            "visible text, important UI elements, "
                            "and anything relevant to understanding "
                            "the current computer state. "
                            "Be concise but specific."
                        )
                    },
                    {
                        "type": "input_image",
                        "image_url": screenshot
                    }
                ]
            }
        ]
    )

    description = response.output_text

    print()
    print("ASTRA'S DESCRIPTION")
    print("-" * 60)
    print(description)
    print("-" * 60)

    return description


def run_agent(task):
    """
    Run the Astra computer-use loop.
    """

    print()
    print("=" * 60)
    print("ASTRA COMPUTER AGENT")
    print("=" * 60)
    print(f"Task: {task}")
    print("=" * 60)

    # ---------------------------------------------------------
    # 1. Initial screenshot
    # ---------------------------------------------------------

    print()
    print("Taking initial screenshot...")

    screenshot = screenshot_data_url()

    # ---------------------------------------------------------
    # 2. Describe initial screenshot
    # ---------------------------------------------------------

    describe_screenshot(screenshot)

    # ---------------------------------------------------------
    # 3. Ask Astra to perform the task
    # ---------------------------------------------------------

    response = client.responses.create(
        model=MODEL,
        reasoning={
            "effort": "high"
        },
        tools=[
            {
                "type": "computer"
            }
        ],
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": task
                    },
                    {
                        "type": "input_image",
                        "image_url": screenshot
                    }
                ]
            }
        ]
    )

    # ---------------------------------------------------------
    # 4. Computer-use loop
    # ---------------------------------------------------------

    while True:

        computer_calls = [
            item
            for item in response.output
            if item.type == "computer_call"
        ]

        if not computer_calls:
            print()
            print("=" * 60)
            print("ASTRA FINISHED")
            print("=" * 60)

            if response.output_text:
                print(response.output_text)

            break

        for computer_call in computer_calls:

            # -------------------------------------------------
            # Safety checks requested by Astra
            # -------------------------------------------------

            pending_safety_checks = getattr(
                computer_call,
                "pending_safety_checks",
                []
            )

            acknowledged_safety_checks = []

            if pending_safety_checks:
                print()
                print("=" * 60)
                print("ASTRA REQUESTED A SAFETY CHECK")
                print("=" * 60)

                for check in pending_safety_checks:

                    print(check)

                    answer = input(
                        "Acknowledge this safety check? [y/N]: "
                    )

                    if answer.lower() != "y":
                        print("Safety check rejected.")
                        return

                    acknowledged_safety_checks.append(check)

            # -------------------------------------------------
            # Get actions
            # -------------------------------------------------

            actions = getattr(
                computer_call,
                "actions",
                None
            )

            if actions is None:
                single_action = getattr(
                    computer_call,
                    "action",
                    None
                )

                actions = (
                    [single_action]
                    if single_action
                    else []
                )

            # -------------------------------------------------
            # Execute every requested action
            # -------------------------------------------------

            for action_object in actions:

                # Convert SDK object into a dictionary.
                if hasattr(action_object, "model_dump"):
                    action = action_object.model_dump(
                        exclude_none=True
                    )
                elif isinstance(action_object, dict):
                    action = action_object
                else:
                    action = vars(action_object)

                # Show action and ask permission.
                if not confirm_action(action):
                    print("Action rejected.")
                    return

                print()
                print("Executing action...")

                execute_computer_action(action)

                # Give the application a moment to update.
                time.sleep(0.5)

            # -------------------------------------------------
            # Capture the new desktop state
            # -------------------------------------------------

            print()
            print("Capturing updated desktop...")

            new_screenshot = screenshot_data_url()

            # -------------------------------------------------
            # Describe the new desktop state
            # -------------------------------------------------

            describe_screenshot(new_screenshot)

            # -------------------------------------------------
            # Send screenshot back to Astra
            # -------------------------------------------------

            computer_output = {
                "type": "computer_call_output",
                "call_id": computer_call.call_id,
                "output": {
                    "type": "computer_screenshot",
                    "image_url": new_screenshot
                }
            }

            if acknowledged_safety_checks:
                computer_output[
                    "acknowledged_safety_checks"
                ] = acknowledged_safety_checks

            response = client.responses.create(
                model=MODEL,
                reasoning={
                    "effort": "high"
                },
                tools=[
                    {
                        "type": "computer"
                    }
                ],
                previous_response_id=response.id,
                input=[
                    computer_output
                ]
            )


# =============================================================
# MAIN PROGRAM
# =============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("GPT-6 ASTRA LOCAL COMPUTER HARNESS")
    print("=" * 60)

    task = input(
        "What would you like Astra to do? "
    ).strip()

    if not task:
        print("No task supplied.")
        raise SystemExit

    run_agent(task)

