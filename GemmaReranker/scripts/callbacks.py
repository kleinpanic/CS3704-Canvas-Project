from transformers import TrainerCallback


class RewardCollapseCallback(TrainerCallback):
    """Halt training when rewards/chosen sustains below threshold for sustained_intervals steps."""

    def __init__(self, threshold: float = -2.0, sustained_intervals: int = 5):
        self.threshold = threshold
        self.sustained = sustained_intervals
        self.below_count = 0

    def on_log(self, args, state, control, logs=None, **kwargs):
        if not logs or "rewards/chosen" not in logs:
            return
        if logs["rewards/chosen"] < self.threshold:
            self.below_count += 1
            if self.below_count >= self.sustained:
                control.should_training_stop = True
        else:
            self.below_count = 0
