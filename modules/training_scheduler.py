from functools import partial
import torch
import transformers
import math
from torch.optim.lr_scheduler import LambdaLR

last_print_label = ''

def _get_fp_cosine_schedule_with_warmup_lr_lambda(current_step: int, *, num_warmup_steps: int, num_training_steps: int, num_firstepoch_steps: int):
    
    global last_print_label
    print_label = ''
    
    if current_step < num_warmup_steps:
        print_label = 'Scheduler: Warmup'
    elif current_step < num_firstepoch_steps:
        print_label = 'Scheduler: Hold'
    else:
        print_label = 'Scheduler: Annealing'
    
    if print_label != last_print_label:
        print(print_label)
    
    last_print_label = print_label

    if current_step < num_warmup_steps:
        return float(current_step) / float(max(1, num_warmup_steps))
    
    if current_step < num_firstepoch_steps:
        return 1.0 
    
    progress = float(current_step - num_firstepoch_steps) / float(max(1, num_training_steps - num_firstepoch_steps))
    num_cycles = 0.5
    return max(0.0, 0.5 * (1.0 + math.cos(math.pi * float(num_cycles) * 2.0 * progress)))    
    

#This scheduler is designed for low epochs 
#in first epoch is behaves as constant scheduler
#in epochs 2,3... it behaves as cosine scheduler

def custom_scheduler_with_warmup(optimizer, num_warmup_steps, num_training_steps, num_firstepoch_steps, last_epoch=-1):
    """
    Args:
        optimizer ([`~torch.optim.Optimizer`]):
            The optimizer for which to schedule the learning rate.
        num_warmup_steps (`int`):
            The number of steps for the warmup phase.
        num_training_steps (`int`):
            The total number of training steps.
        last_epoch (`int`, *optional*, defaults to -1):
            The index of the last epoch when resuming training.

    Return:
        `torch.optim.lr_scheduler.LambdaLR` with the appropriate schedule.
    """
    
    lr_lambda = partial(
        _get_fp_cosine_schedule_with_warmup_lr_lambda,
        num_warmup_steps=num_warmup_steps,
        num_training_steps=num_training_steps,
        num_firstepoch_steps = num_firstepoch_steps,
    )
    return LambdaLR(optimizer, lr_lambda, last_epoch)

class FPSchedulerTrainer(transformers.Trainer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def create_scheduler(self, num_training_steps: int, optimizer: torch.optim.Optimizer = None):
        #Setup the scheduler. The optimizer of the trainer must have been set up either before this method is called or passed as an argument.
        
        if self.args.lr_scheduler_type == 'cosine':
            num_train_epochs = self.args.num_train_epochs
            num_warmup_steps=self.args.get_warmup_steps(num_training_steps)
            num_firstepoch_steps = math.ceil(num_training_steps/num_train_epochs)
            num_warmup_acc = num_warmup_steps*self.args.gradient_accumulation_steps
            num_firstepoch_steps_acc = num_firstepoch_steps*self.args.gradient_accumulation_steps
            num_training_steps_acc = num_training_steps*self.args.gradient_accumulation_steps
            print (f"FP Scheduler Warm up: 0-{num_warmup_acc}, Hold {num_warmup_acc}-{num_firstepoch_steps_acc}, Annealing {num_firstepoch_steps_acc}-{num_training_steps_acc}")
            self.lr_scheduler = custom_scheduler_with_warmup(
                    optimizer=self.optimizer if optimizer is None else optimizer,
                    num_warmup_steps=num_warmup_steps,
                    num_training_steps=num_training_steps, 
                    num_firstepoch_steps = num_firstepoch_steps,
                )
            self._created_lr_scheduler = True
            return self.lr_scheduler
        else:
            return  super().create_scheduler(num_training_steps=num_training_steps, optimizer=optimizer)
