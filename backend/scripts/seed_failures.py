"""Seed the demo batch: ~100 mixed-class failed payments through test mode.

    python -m scripts.seed_failures --count 100 --seed 42

Class mix should roughly reflect the Indian market rather than being uniform
— insufficient funds dominates mandate failures, technical declines cluster
on specific banks. State the chosen mix in the README; a demo that names its
assumptions beats one that hides them.

Must include at least one HARD_DECLINE case flagged to run with the loose
prompt, so the gate is observed blocking a retry on screen. That is the
3:00 beat of the video.
"""


def main() -> None:
    """Generate failures, POST them at the webhook route with valid
    signatures, and report the resulting arm split so the operator can see
    the holdout is roughly 20% before the demo starts."""
    raise NotImplementedError("step-08: batch seeder")


if __name__ == "__main__":
    main()
