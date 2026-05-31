import subprocess
import sys
import tempfile
import textwrap
import pickle
from pathlib import Path
from langchain.tools import tool

SESSIONS_DIR = Path(__file__).parent.parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


class StatefulInterpreter:
    """
    Provides a stateful Python code execution tool that persists session state
    between invocations within the same run/node/clone context.

    Session isolation key: f"{run_id}:{node_id}:{clone_id}"
    State stored in: sessions/{session_key}.pkl

    Uses a Python subprocess for isolation. QuickJS was intentionally removed
    because it was half-implemented (no session persistence) and added complexity
    without benefit.
    """

    @staticmethod
    def _session_path(session_key: str) -> Path:
        safe_key = session_key.replace(":", "_").replace("/", "_")
        return SESSIONS_DIR / f"{safe_key}.pkl"

    @staticmethod
    def _load_session(session_key: str) -> dict:
        path = StatefulInterpreter._session_path(session_key)
        if path.exists():
            with open(path, "rb") as f:
                return pickle.load(f)
        return {}

    @staticmethod
    def execute_python(code_str: str, session_key: str, timeout: int = 10) -> str:
        """Execute Python code in an isolated subprocess with persisted session state."""
        session_path = str(StatefulInterpreter._session_path(session_key))

        script = textwrap.dedent(f"""
import pickle, sys, os

session_path = {repr(session_path)}
if os.path.exists(session_path):
    with open(session_path, 'rb') as f:
        namespace = pickle.load(f)
else:
    namespace = {{}}

try:
    exec({repr(code_str)}, namespace)
    safe_ns = {{k: v for k, v in namespace.items()
               if not k.startswith('__') and isinstance(v, (str, int, float, bool, list, dict, type(None)))}}
    with open(session_path, 'wb') as f:
        pickle.dump(safe_ns, f)
    print("__STATUS__:ok")
except Exception as e:
    print(f"__ERROR__:{{e}}", file=sys.stderr)
    sys.exit(1)
""")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                return f"Error: {result.stderr.strip()}"
            output = result.stdout.strip().replace("__STATUS__:ok", "").strip()
            return output or "Code executed successfully."
        except subprocess.TimeoutExpired:
            return f"Error: Code execution timed out after {timeout} seconds."
        finally:
            Path(script_path).unlink(missing_ok=True)

    @classmethod
    def make_tool(cls, session_key: str):
        """Factory: returns a LangChain tool bound to a specific session key."""

        @tool
        def execute_code(code: str) -> str:
            """Execute Python code and return the output. State (variables) is preserved between calls within the same session."""
            return cls.execute_python(code, session_key)

        return execute_code
