import curses
import time
import random

# Game constants
PADDLE_CHAR = '█'
BALL_CHAR = 'o'
BRICK_CHAR = '▣'
EMPTY_CHAR = ' '

class GameObject:
    def __init__(self, y, x, char):
        self.y = y
        self.x = x
        self.char = char

    def draw(self, stdscr):
        try:
            stdscr.addch(int(self.y), int(self.x), self.char)
        except curses.error:
            pass

class Paddle(GameObject):
    def __init__(self, y, x, width):
        super().__init__(y, x, PADDLE_CHAR * width)
        self.width = width

    def draw(self, stdscr):
        try:
            stdscr.addstr(int(self.y), int(self.x), self.char)
        except curses.error:
            pass

    def move(self, direction, max_x):
        if direction == "left" and self.x > 1:
            self.x -= 2
        elif direction == "right" and self.x < max_x - self.width - 1:
            self.x += 2

class Ball(GameObject):
    def __init__(self, y, x):
        super().__init__(y, x, BALL_CHAR)
        self.vy = -1  # Vertical velocity
        self.vx = 2   # Horizontal velocity

    def move(self):
        self.y += self.vy
        self.x += self.vx

    def bounce_y(self):
        self.vy *= -1

    def bounce_x(self):
        self.vx *= -1

class Brick(GameObject):
    def __init__(self, y, x):
        super().__init__(y, x, BRICK_CHAR)
        self.active = True

    def draw(self, stdscr):
        if self.active:
            try:
                stdscr.addch(int(self.y), int(self.x), self.char)
            except curses.error:
                pass

class PowerUp(GameObject):
    def __init__(self, y, x, type):
        super().__init__(y, x, type)
        self.type = type
        self.active = True

    def move(self):
        self.y += 1 # Power-ups fall downwards

def create_bricks(rows, cols, start_y, start_x):
    bricks = []
    for r in range(rows):
        for c in range(cols):
            bricks.append(Brick(start_y + r, start_x + c * 2))
    return bricks

def main(stdscr):
    # Setup screen
    curses.curs_set(0)
    stdscr.nodelay(1)
    stdscr.timeout(100) # Refresh rate in ms

    # Get screen dimensions
    height, width = stdscr.getmaxyx()

    # Create game objects
    paddle_width = 10
    paddle = Paddle(height - 3, width // 2 - paddle_width // 2, paddle_width)
    ball = Ball(height - 4, width // 2)
    bricks = create_bricks(4, (width - 4) // 2, 2, 2)
    power_ups = []

    score = 0
    lives = 3
    game_over = False

    while not game_over:
        # Get user input
        key = stdscr.getch()

        if key == curses.KEY_LEFT:
            paddle.move("left", width)
        elif key == curses.KEY_RIGHT:
            paddle.move("right", width)
        elif key == ord('q') or key == 27: # Quit on 'q' or ESC
            break

        # Update game state
        ball.move()

        # Ball collision with walls
        if ball.x < 1:
            ball.x = 1
            ball.bounce_x()
        elif ball.x >= width - 1:
            ball.x = width - 2
            ball.bounce_x()

        if ball.y < 1:
            ball.y = 1
            ball.bounce_y()

        # Ball collision with paddle
        if (paddle.y <= ball.y <= paddle.y + 1) and (paddle.x <= ball.x < paddle.x + paddle.width):
            ball.bounce_y()
            # Add slight angle based on where it hits the paddle
            ball.vx += (ball.x - (paddle.x + paddle.width / 2)) / (paddle.width / 4)


        # Ball collision with bricks
        for brick in bricks:
            if brick.active and (brick.y == int(ball.y) and brick.x <= int(ball.x) <= brick.x + 1):
                brick.active = False
                ball.bounce_y()
                score += 10
                # Add a chance for a power-up
                if random.random() < 0.2: # 20% chance
                    power_ups.append(PowerUp(brick.y, brick.x, random.choice(['E', 'S', 'P'])))


        # Update and draw power-ups
        for power_up in power_ups:
            power_up.move()
            power_up.draw(stdscr)

            # Check for paddle collision
            if (paddle.y <= power_up.y <= paddle.y + 1) and (paddle.x <= power_up.x < paddle.x + paddle.width):
                power_up.active = False
                # Apply power-up effect
                if power_up.type == 'E': # Enlarge
                    paddle.width = min(paddle.width + 4, width - 2)
                    paddle.char = PADDLE_CHAR * paddle.width
                elif power_up.type == 'S': # Slow
                    stdscr.timeout(150) # Slower refresh rate
                elif power_up.type == 'P': # Player
                    lives += 1

        # Remove inactive power-ups
        power_ups = [p for p in power_ups if p.active and p.y < height -1]


        # Ball missed
        if ball.y >= height - 1:
            lives -= 1
            if lives <= 0:
                game_over = True
            else:
                # Reset ball and paddle
                ball.y = height - 4
                ball.x = width // 2
                ball.vy = -1
                paddle.x = width // 2 - paddle_width // 2
                stdscr.timeout(100) # Reset speed

        # Drawing
        stdscr.clear()
        stdscr.addstr(0, 2, f"Score: {score}  Lives: {lives}")
        paddle.draw(stdscr)
        ball.draw(stdscr)
        for brick in bricks:
            brick.draw(stdscr)
        for power_up in power_ups:
            power_up.draw(stdscr)
        stdscr.refresh()

    # Game Over screen
    if game_over:
        stdscr.nodelay(0) # Wait for user input
        h, w = stdscr.getmaxyx()
        msg = "Game Over!"
        msg2 = f"Final Score: {score}"
        msg3 = "Press any key to exit."
        stdscr.addstr(h//2 - 1, w//2 - len(msg)//2, msg)
        stdscr.addstr(h//2, w//2 - len(msg2)//2, msg2)
        stdscr.addstr(h//2 + 2, w//2 - len(msg3)//2, msg3)
        stdscr.getch()


if __name__ == '__main__':
    curses.wrapper(main)