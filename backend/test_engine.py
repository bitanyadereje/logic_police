from main import analyze_argument


def run(name, text, expect_valid):
    print("\n--- " + name + " ---")
    result = analyze_argument(text)
    actual = result.get("valid", False)
    status = "PASS" if actual == expect_valid else "FAIL"
    print("Expected: " + ("VALID" if expect_valid else "INVALID"))
    print("Actual:   " + ("VALID" if actual else "INVALID") + "  [" + status + "]")
    print("Premises: " + str(len(result.get("premises", []))))
    print("Conclusion: " + result.get("conclusion", "")[:80])


run(
    "Complete Socrates syllogism",
    "All humans are mortal. Socrates is human. Therefore, Socrates is mortal.",
    True,
)

run(
    "Missing premise",
    "Socrates is a man. Therefore, Socrates is mortal.",
    False,
)

run(
    "Modus ponens",
    "If it rains, the ground is wet. It is raining. Therefore, the ground is wet.",
    True,
)

run(
    "Affirming the consequent",
    "If it rains, the ground is wet. The ground is wet. Therefore, it rained.",
    False,
)

run(
    "Ad hominem",
    "You can't trust anything he says because he's a politician.",
    False,
)

print("\n--- All tests done ---")