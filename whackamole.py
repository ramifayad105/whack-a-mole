import pygame
import random
import sys
import math

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)

# ── Constants ──────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 900, 700
FPS = 60

# Colours
BG_TOP       = ( 34, 139,  34)
BG_BOT       = ( 20,  90,  20)
DIRT         = (139,  90,  43)
DIRT_DARK    = ( 90,  55,  20)
HOLE_COLOR   = ( 30,  15,   5)
MOLE_BODY    = (139,  90,  43)
MOLE_FACE    = (200, 150, 100)
MOLE_NOSE    = (220,  80,  80)
MOLE_EYE     = ( 20,  20,  20)
MOLE_SHINE   = (255, 255, 255)
WHACKED_COL  = (255,  80,  80)
GOLD         = (255, 215,   0)
WHITE        = (255, 255, 255)
BLACK        = (  0,   0,   0)
RED          = (220,  50,  50)
GREEN        = ( 50, 200,  50)
BLUE         = ( 50, 120, 220)
ORANGE       = (255, 140,   0)

# Grid
COLS, ROWS   = 3, 3
HOLE_R       = 60
HOLE_RY      = 22
MOLE_W       = 80
MOLE_H       = 90

# Timing
MOLE_UP_MIN  = 0.6
MOLE_UP_MAX  = 1.4
MOLE_RISE    = 0.18
GAME_DURATION = 60

# ── Fullscreen manager ─────────────────────────────────────────────────────────

class Display:
    """Wraps the pygame window and handles windowed / fullscreen toggling.

    All game code draws onto a fixed 900×700 canvas (self.canvas).
    Each frame, canvas is scaled to fill the real window and blitted.
    Mouse coordinates are automatically translated back to canvas space.
    """

    def __init__(self):
        self.fullscreen = False
        self.window     = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption('Whack-a-Mole  |  F11 / Alt+Enter = Fullscreen')
        self.canvas     = pygame.Surface((WIDTH, HEIGHT))
        self._update_scale()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self._update_scale()

    def _update_scale(self):
        ww, wh = self.window.get_size()
        # letterbox: keep aspect ratio
        scale = min(ww / WIDTH, wh / HEIGHT)
        self.scaled_w = int(WIDTH  * scale)
        self.scaled_h = int(HEIGHT * scale)
        self.offset_x = (ww - self.scaled_w) // 2
        self.offset_y = (wh - self.scaled_h) // 2
        self.scale    = scale

    def translate_mouse(self, pos):
        """Convert real window mouse pos → canvas pos."""
        mx = (pos[0] - self.offset_x) / self.scale
        my = (pos[1] - self.offset_y) / self.scale
        return (int(mx), int(my))

    def flip(self):
        ww, wh = self.window.get_size()
        self._update_scale()
        scaled = pygame.transform.scale(self.canvas, (self.scaled_w, self.scaled_h))
        self.window.fill(BLACK)
        self.window.blit(scaled, (self.offset_x, self.offset_y))
        pygame.display.flip()

    def handle_event(self, event):
        """Return True if the event was consumed (fullscreen toggle)."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                self.toggle_fullscreen()
                return True
            if event.key == pygame.K_RETURN and (event.mod & pygame.KMOD_ALT):
                self.toggle_fullscreen()
                return True
        if event.type == pygame.VIDEORESIZE:
            if not self.fullscreen:
                self.window = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            self._update_scale()
            return True
        return False


# ── Helpers ────────────────────────────────────────────────────────────────────

def lerp(a, b, t):
    return a + (b - a) * t

def ease_out(t):
    return 1 - (1 - t) ** 2

def ease_in(t):
    return t * t

# ── Simple synthesised sounds ──────────────────────────────────────────────────

def _make_tone(freq, duration, volume=0.4):
    sample_rate = 44100
    n = int(sample_rate * duration)
    import array as _array
    buf = _array.array('h', [0] * n)
    for i in range(n):
        fade = 1.0 if i < n * 0.8 else (n - i) / max(1, n * 0.2)
        val  = int(32767 * volume * fade * math.sin(2 * math.pi * freq * i / sample_rate))
        buf[i] = max(-32768, min(32767, val))
    sound = pygame.sndarray.make_sound(
        pygame.surfarray.make_surface(
            __import__('numpy').array(buf, dtype='<i2').reshape(-1, 1)
            * __import__('numpy').ones((1, 2), dtype='<i2')
        )
    )
    return sound

try:
    import numpy as _np
    HIT_SOUND  = _make_tone(600, 0.07, 0.5)
    MISS_SOUND = _make_tone(200, 0.12, 0.3)
    POP_SOUND  = _make_tone(880, 0.05, 0.3)
except Exception:
    class _Silent:
        def play(self): pass
    HIT_SOUND = MISS_SOUND = POP_SOUND = _Silent()

# ── Mole ───────────────────────────────────────────────────────────────────────

class Mole:
    def __init__(self, cx, cy):
        self.cx = cx
        self.cy = cy
        self.state       = 'hidden'
        self.anim_t      = 0.0
        self.up_timer    = 0.0
        self.up_duration = 1.0
        self.whacked     = False
        self.whack_flash = 0.0

    @property
    def offset(self):
        if self.state == 'hidden':  return 0
        if self.state == 'rising':  return int(ease_out(self.anim_t) * MOLE_H * 0.85)
        if self.state == 'up':      return int(MOLE_H * 0.85)
        if self.state == 'falling': return int((1 - ease_in(self.anim_t)) * MOLE_H * 0.85)
        return 0

    def update(self, dt):
        if self.state == 'rising':
            self.anim_t += dt / MOLE_RISE
            if self.anim_t >= 1.0:
                self.anim_t = 0.0
                self.state  = 'up'
                POP_SOUND.play()
        elif self.state == 'up':
            self.up_timer += dt
            if self.up_timer >= self.up_duration:
                self.state  = 'falling'
                self.anim_t = 0.0
        elif self.state == 'falling':
            self.anim_t += dt / MOLE_RISE
            if self.anim_t >= 1.0:
                self.state   = 'hidden'
                self.whacked = False
                self.anim_t  = 0.0
        if self.whack_flash > 0:
            self.whack_flash -= dt

    def pop(self, duration):
        if self.state == 'hidden':
            self.state       = 'rising'
            self.anim_t      = 0.0
            self.up_timer    = 0.0
            self.up_duration = duration
            self.whacked     = False

    def try_whack(self, mx, my):
        if self.state not in ('rising', 'up'):
            return False
        off = self.offset
        rx  = self.cx - MOLE_W // 2
        ry  = self.cy - off - MOLE_H + HOLE_RY
        if rx <= mx <= rx + MOLE_W and ry <= my <= ry + MOLE_H:
            self.whacked     = True
            self.whack_flash = 0.25
            self.state       = 'falling'
            self.anim_t      = 0.0
            return True
        return False

    def draw(self, surf):
        off = self.offset
        if off <= 0:
            return
        cx, cy = self.cx, self.cy

        clip_rect = pygame.Rect(cx - MOLE_W, cy - MOLE_H * 2, MOLE_W * 2, MOLE_H * 2 + HOLE_RY)
        old_clip  = surf.get_clip()
        surf.set_clip(clip_rect)

        body_color = WHACKED_COL if self.whack_flash > 0 else MOLE_BODY
        face_color = WHACKED_COL if self.whack_flash > 0 else MOLE_FACE

        body_rect = pygame.Rect(cx - MOLE_W // 2,
                                cy - off - MOLE_H + HOLE_RY,
                                MOLE_W, MOLE_H)
        pygame.draw.ellipse(surf, body_color, body_rect)

        face_rect = pygame.Rect(cx - MOLE_W // 2 + 6,
                                cy - off - MOLE_H + HOLE_RY,
                                MOLE_W - 12, MOLE_H * 2 // 3)
        pygame.draw.ellipse(surf, face_color, face_rect)

        ey = cy - off - MOLE_H + HOLE_RY + MOLE_H // 4
        for ex in (cx - 14, cx + 14):
            pygame.draw.circle(surf, MOLE_EYE,   (ex, ey), 7)
            pygame.draw.circle(surf, MOLE_SHINE, (ex - 2, ey - 2), 2)

        pygame.draw.ellipse(surf, MOLE_NOSE,
                            pygame.Rect(cx - 8,
                                        cy - off - MOLE_H + HOLE_RY + MOLE_H // 2 - 4,
                                        16, 10))

        wy = cy - off - MOLE_H + HOLE_RY + MOLE_H // 2 + 2
        for dx, sign in ((-10, -1), (10, 1)):
            for i in range(3):
                ex2 = cx + sign * (30 + i * 5)
                ey2 = wy + (i - 1) * 5
                pygame.draw.line(surf, DIRT_DARK, (cx + dx, wy), (ex2, ey2), 1)

        surf.set_clip(old_clip)


# ── Drawing helpers ────────────────────────────────────────────────────────────

def draw_hole(surf, cx, cy):
    pygame.draw.ellipse(surf, HOLE_COLOR,
                        pygame.Rect(cx - HOLE_R, cy - HOLE_RY, HOLE_R * 2, HOLE_RY * 2))
    pygame.draw.ellipse(surf, DIRT_DARK,
                        pygame.Rect(cx - HOLE_R, cy - HOLE_RY, HOLE_R * 2, HOLE_RY * 2), 3)


def draw_dirt_mound(surf, cx, cy):
    pts = [(cx - HOLE_R - 10, cy + 4),
           (cx - HOLE_R + 10, cy - 8),
           (cx,               cy - 14),
           (cx + HOLE_R - 10, cy - 8),
           (cx + HOLE_R + 10, cy + 4)]
    pygame.draw.polygon(surf, DIRT, pts)
    pygame.draw.polygon(surf, DIRT_DARK, pts, 2)


def draw_background(surf):
    for y in range(HEIGHT):
        t   = y / HEIGHT
        col = (int(lerp(BG_TOP[0], BG_BOT[0], t)),
               int(lerp(BG_TOP[1], BG_BOT[1], t)),
               int(lerp(BG_TOP[2], BG_BOT[2], t)))
        pygame.draw.line(surf, col, (0, y), (WIDTH, y))
    random.seed(42)
    for _ in range(40):
        gx = random.randint(0, WIDTH)
        gy = random.randint(HEIGHT // 3, HEIGHT - 20)
        for blade in range(3):
            bx = gx + blade * 5 - 5
            pygame.draw.line(surf, (50, 160, 50),
                             (bx, gy),
                             (bx + random.randint(-3, 3), gy - random.randint(8, 18)), 2)


def draw_button(surf, text, cx, cy, w, h, color, hover_color, font, mouse_pos=None):
    if mouse_pos is None:
        mouse_pos = pygame.mouse.get_pos()
    rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    col  = hover_color if rect.collidepoint(mouse_pos) else color
    pygame.draw.rect(surf, col, rect, border_radius=12)
    pygame.draw.rect(surf, WHITE, rect, 2, border_radius=12)
    t = font.render(text, True, WHITE)
    surf.blit(t, (cx - t.get_width() // 2, cy - t.get_height() // 2))
    return rect


def draw_hud(surf, score, time_left, combo, high_score):
    font_big = pygame.font.SysFont('Arial', 36, bold=True)
    font_med = pygame.font.SysFont('Arial', 24, bold=True)
    font_sm  = pygame.font.SysFont('Arial', 16)

    bar = pygame.Surface((WIDTH, 60), pygame.SRCALPHA)
    bar.fill((0, 0, 0, 160))
    surf.blit(bar, (0, 0))

    surf.blit(font_big.render(f'Score: {score}', True, GOLD), (20, 12))

    col = RED if time_left <= 10 else WHITE
    t   = font_big.render(f'Time: {int(time_left)}s', True, col)
    surf.blit(t, (WIDTH // 2 - t.get_width() // 2, 12))

    t = font_med.render(f'Best: {high_score}', True, (180, 180, 255))
    surf.blit(t, (WIDTH - t.get_width() - 20, 18))

    # fullscreen hint (bottom-right corner)
    hint = font_sm.render('F11 = Fullscreen', True, (150, 150, 150))
    surf.blit(hint, (WIDTH - hint.get_width() - 8, HEIGHT - hint.get_height() - 6))

    if combo >= 2:
        t = font_med.render(f'x{combo} COMBO!', True, ORANGE)
        surf.blit(t, (WIDTH // 2 - t.get_width() // 2, 65))


# ── Floating score text ────────────────────────────────────────────────────────

class FloatText:
    def __init__(self, text, x, y, color=GOLD):
        self.text  = text
        self.x, self.y = x, y
        self.color = color
        self.life  = 0.8
        self.age   = 0.0

    def update(self, dt):
        self.age += dt
        self.y   -= 60 * dt

    @property
    def alive(self):
        return self.age < self.life

    def draw(self, surf):
        alpha = int(255 * (1 - self.age / self.life))
        font  = pygame.font.SysFont('Arial', 28, bold=True)
        txt   = font.render(self.text, True, self.color)
        txt.set_alpha(alpha)
        surf.blit(txt, (self.x - txt.get_width() // 2, int(self.y)))


# ── Screens ────────────────────────────────────────────────────────────────────

def draw_menu_screen(surf, high_score, mouse_pos):
    draw_background(surf)
    font_title = pygame.font.SysFont('Impact', 80)
    font_sub   = pygame.font.SysFont('Arial', 30, bold=True)
    font_sm    = pygame.font.SysFont('Arial', 22)
    font_hint  = pygame.font.SysFont('Arial', 16)

    shadow = font_title.render('WHACK-A-MOLE', True, BLACK)
    surf.blit(shadow, (WIDTH // 2 - shadow.get_width() // 2 + 4, 104))
    title = font_title.render('WHACK-A-MOLE', True, GOLD)
    surf.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))

    dummy = Mole(WIDTH // 2, HEIGHT // 2 + 30)
    dummy.state = 'up'
    draw_dirt_mound(surf, WIDTH // 2, HEIGHT // 2 + 30)
    draw_hole(surf, WIDTH // 2, HEIGHT // 2 + 30)
    dummy.draw(surf)

    btn_play = draw_button(surf, 'PLAY', WIDTH // 2, HEIGHT - 210, 200, 55,
                           GREEN, (30, 160, 30), font_sub, mouse_pos)
    btn_fs   = draw_button(surf, 'FULLSCREEN  [F11]', WIDTH // 2, HEIGHT - 145, 260, 50,
                           BLUE, (30, 80, 180), font_sm, mouse_pos)
    btn_quit = draw_button(surf, 'QUIT', WIDTH // 2, HEIGHT - 85, 200, 55,
                           RED, (160, 30, 30), font_sub, mouse_pos)

    if high_score > 0:
        hs = font_sm.render(f'High Score: {high_score}', True, GOLD)
        surf.blit(hs, (WIDTH // 2 - hs.get_width() // 2, HEIGHT - 40))

    hint = font_hint.render('Alt+Enter also toggles fullscreen', True, (130, 130, 130))
    surf.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 18))

    return btn_play, btn_fs, btn_quit


def draw_gameover_screen(surf, score, high_score, mouse_pos):
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surf.blit(overlay, (0, 0))

    font_big = pygame.font.SysFont('Impact', 72)
    font_med = pygame.font.SysFont('Arial', 36, bold=True)
    font_sub = pygame.font.SysFont('Arial', 28, bold=True)

    t = font_big.render('GAME OVER', True, RED)
    surf.blit(t, (WIDTH // 2 - t.get_width() // 2, 160))

    t = font_med.render(f'Your Score: {score}', True, WHITE)
    surf.blit(t, (WIDTH // 2 - t.get_width() // 2, 270))

    if score >= high_score:
        t = font_med.render('NEW HIGH SCORE!', True, GOLD)
        surf.blit(t, (WIDTH // 2 - t.get_width() // 2, 320))

    t = font_med.render(f'Best: {high_score}', True, (180, 180, 255))
    surf.blit(t, (WIDTH // 2 - t.get_width() // 2, 370))

    btn_play = draw_button(surf, 'PLAY AGAIN', WIDTH // 2, 460, 240, 55,
                           GREEN, (30, 160, 30), font_sub, mouse_pos)
    btn_menu = draw_button(surf, 'MENU', WIDTH // 2, 530, 240, 55,
                           BLUE, (30, 80, 180), font_sub, mouse_pos)
    btn_quit = draw_button(surf, 'QUIT', WIDTH // 2, 600, 240, 55,
                           RED, (160, 30, 30), font_sub, mouse_pos)
    return btn_play, btn_menu, btn_quit


# ── Game loop ──────────────────────────────────────────────────────────────────

def build_positions():
    margin_x = 130
    margin_y = 180
    gap_x    = (WIDTH  - 2 * margin_x) // (COLS - 1)
    gap_y    = (HEIGHT - 2 * margin_y) // (ROWS - 1)
    return [(margin_x + c * gap_x, margin_y + r * gap_y)
            for r in range(ROWS) for c in range(COLS)]


def run_game(display, clock, high_score):
    positions = build_positions()
    moles     = [Mole(cx, cy) for cx, cy in positions]
    surf      = display.canvas

    bg_surf = pygame.Surface((WIDTH, HEIGHT))
    draw_background(bg_surf)

    score     = 0
    combo     = 0
    time_left = float(GAME_DURATION)
    floats    = []
    next_pop  = 0.5
    game_over = False

    while True:
        dt        = min(clock.tick(FPS) / 1000.0, 0.05)
        mouse_pos = display.translate_mouse(pygame.mouse.get_pos())

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return 'quit', score
            if display.handle_event(event):
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return 'menu', score

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                canvas_pos = display.translate_mouse(event.pos)
                if game_over:
                    btn_play, btn_menu, btn_quit = draw_gameover_screen(
                        surf, score, high_score, mouse_pos)
                    if btn_play.collidepoint(canvas_pos): return 'play', score
                    if btn_menu.collidepoint(canvas_pos): return 'menu', score
                    if btn_quit.collidepoint(canvas_pos): return 'quit', score
                else:
                    mx, my = canvas_pos
                    hit = False
                    for mole in moles:
                        if mole.try_whack(mx, my):
                            combo += 1
                            pts    = 10 * combo
                            score += pts
                            col    = ORANGE if combo >= 3 else GOLD
                            floats.append(FloatText(f'+{pts}', mx, my, col))
                            HIT_SOUND.play()
                            hit = True
                            break
                    if not hit and my > 60:
                        combo = 0
                        MISS_SOUND.play()

        if not game_over:
            time_left -= dt
            if time_left <= 0:
                time_left  = 0
                game_over  = True
                high_score = max(high_score, score)

            elapsed    = GAME_DURATION - time_left
            speed_mul  = 1.0 + elapsed / 60.0
            active_max = min(2 + int(elapsed / 20), 5)

            for mole in moles:
                mole.update(dt)

            next_pop -= dt
            if next_pop <= 0:
                hidden = [m for m in moles if m.state == 'hidden']
                active = sum(1 for m in moles if m.state != 'hidden')
                if hidden and active < active_max:
                    m   = random.choice(hidden)
                    dur = random.uniform(MOLE_UP_MIN, MOLE_UP_MAX) / speed_mul
                    m.pop(dur)
                next_pop = random.uniform(0.3, 0.8) / speed_mul

            for ft in floats:
                ft.update(dt)
            floats = [ft for ft in floats if ft.alive]

        # ── Render to canvas ──
        surf.blit(bg_surf, (0, 0))
        for cx, cy in positions:
            draw_dirt_mound(surf, cx, cy)
        for cx, cy in positions:
            draw_hole(surf, cx, cy)
        for mole in moles:
            mole.draw(surf)
        draw_hud(surf, score, time_left, combo, high_score)
        for ft in floats:
            ft.draw(surf)

        if game_over:
            draw_gameover_screen(surf, score, high_score, mouse_pos)

        display.flip()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    display    = Display()
    clock      = pygame.time.Clock()
    high_score = 0
    state      = 'menu'

    while True:
        if state == 'menu':
            clock.tick(FPS)
            mouse_pos = display.translate_mouse(pygame.mouse.get_pos())
            surf      = display.canvas
            surf.fill(BLACK)
            btn_play, btn_fs, btn_quit = draw_menu_screen(surf, high_score, mouse_pos)
            display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if display.handle_event(event):
                    continue
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    canvas_pos = display.translate_mouse(event.pos)
                    if btn_play.collidepoint(canvas_pos):
                        state = 'play'
                    if btn_fs.collidepoint(canvas_pos):
                        display.toggle_fullscreen()
                    if btn_quit.collidepoint(canvas_pos):
                        pygame.quit(); sys.exit()

        elif state == 'play':
            result, last_score = run_game(display, clock, high_score)
            high_score = max(high_score, last_score)
            state = result
            if state == 'quit':
                pygame.quit(); sys.exit()


if __name__ == '__main__':
    main()
