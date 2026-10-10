"""SAFE NUMBERS TEST (seconds): NaN, infinity and strange values must never crash a number display."""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import safe_numbers as sn
import advanced
import dashboard

passed, failed = 0, []
def check(ok, message):
    global passed
    if ok: passed += 1
    else: failed.append(message)

for value in (3, 3.0, -2, 0, 0.0, 1e15, np.float64(4.0), np.int64(5), np.float32(7.0), True):
    check(sn.is_whole(value) is True, f"is_whole({value!r}) should be True")
for value in (3.5, -0.1, 1e-9, float("nan"), float("inf"), float("-inf"), "abc", None, [], {}, np.nan, np.float64("inf")):
    check(sn.is_whole(value) is False, f"is_whole({value!r}) should be False")
for value in (0, 1, -1e300, 2.5, np.float64(3), True):
    check(sn.is_finite(value) is True, f"is_finite({value!r}) should be True")
for value in (float("nan"), float("inf"), float("-inf"), "x", None, [1]):
    check(sn.is_finite(value) is False, f"is_finite({value!r}) should be False")

# every number display survives the worst values and keeps its normal output
for bad in (float("nan"), float("inf"), float("-inf")):
    for name, function in (("compact", dashboard.compact), ("full_number", dashboard.full_number), ("fmt", advanced.fmt)):
        try:
            text = function(bad)
            check(isinstance(text, str) and text != "", f"{name}({bad}) gave {text!r}")
        except Exception as error:
            check(False, f"{name}({bad}) crashed: {type(error).__name__}")
    try:
        advanced.py(bad)
    except Exception as error:
        check(False, f"advanced.py({bad}) crashed: {type(error).__name__}")
check(dashboard.compact(float("nan")) == "n/a" and dashboard.compact(float("inf")) == "n/a", "compact: NaN and infinity must show n/a")
check(dashboard.full_number(float("nan")) == "n/a" and dashboard.full_number(float("-inf")) == "n/a", "full_number: NaN and infinity must show n/a")
check(advanced.fmt(float("nan")) == "n/a", "fmt: NaN must show n/a")
check(dashboard.compact(11846727) == "11.8M" and dashboard.compact(34500) == "34,500" and dashboard.compact(170.01) == "170.01" and dashboard.compact(2.5e9) == "2.5B", "compact: normal values changed")
check(dashboard.compact(150000) == "150K" and dashboard.compact(-34500) == "-34,500", "compact: thousands or negatives changed")
check(dashboard.full_number(1234567) == "1,234,567" and dashboard.full_number(2.5) == "2.50", "full_number: normal values changed")
check(advanced.fmt(5) == "5" and advanced.fmt(1234.5) == "1,234.50" and advanced.py(4.0) == 4 and isinstance(advanced.py(4.0), int) and advanced.py(4.5) == 4.5, "advanced: formatting changed")
print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:8]: print("  FAIL:", f)
