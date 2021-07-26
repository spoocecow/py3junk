"""
idea: a little robot that walks around based on chat input
n,u move north/up, w/l move left, e/r move right, s/d move down
move after certain count / time
"""
import random
import time

def msg_to_move_vector(msg: str) -> complex:
    m = msg.lower()
    x = m.count('e') + m.count('r') - m.count('w') - m.count('l')
    y = m.count('n') + m.count('u') - m.count('s') - m.count('d')
    x *= 0.9 * m.count('.')
    y *= 0.9 * m.count('.')
    return (x*1i) + (y*1j)


def get_messages():
    return ['test string wow wahoo']


def move(vector: complex):
    # todo lol
    pass


def process():
    vec = 0i+0j
    last_time = time.time()
    while True:
        time.sleep(0.25)
        for m in get_messages():
            vec += msg_to_move_vector(m)
        if abs(vec) > 10 or random.random() < 0.1 or time.time() - last_time > 20:
            move(vec)
            vec = 0i+0j
            last_time = time.time()