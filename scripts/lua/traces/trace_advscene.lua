-- trace_advscene.lua : 어드벤처 씬 디코드 캡처.
--   디코더 루틴 진입 $C0:39D5 마다 소스포인터(DP $0A:$0C = 압축원본)·A(길이/씬id?)·
--   출력버퍼 포인터를 기록 → 특정 씬(사용자가 플레이로 도달)의 압축 ROM 소스 확정.
--   산출 tmp/trace/adv_scene.txt (씬별 소스 주소 목록, 중복 제거)
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local seen = {}
local rows = {}
emu.addMemoryCallback(function()
  local st = emu.getState()
  local d = st["cpu.d"]
  local function r16(a) return emu.read(d + a, emu.memType.snesWorkRam) + emu.read(d + a + 1, emu.memType.snesWorkRam) * 256 end
  local src_addr = r16(0x0A)
  local src_bank = emu.read(d + 0x0C, emu.memType.snesWorkRam)
  local key = string.format("%02X%04X", src_bank, src_addr)
  if not seen[key] then
    seen[key] = true
    rows[#rows + 1] = string.format("f=%-6d src=$%02X:%04X  A=%04X  (pc=0x%06X)",
      st["frameCount"], src_bank, src_addr, st["cpu.a"], ((src_bank % 0x40) * 0x10000) + src_addr)
    local f = io.open(ROOT .. "adv_scene.txt", "w")
    if f then f:write("# 어드벤처 씬 소스(고유). 사용자 플레이로 도달한 씬들.\n")
      for _, s in ipairs(rows) do f:write(s .. "\n") end; f:close() end
  end
end, emu.callbackType.exec, 0xC039D5, 0xC039D5, emu.cpuType.snes, emu.memType.snesMemory)

-- 인트로 자동 진행: 주기적으로 A/Start 눌러 대사 넘김(디코드는 유지되게 천천히)
local function press(btn, on)
  local ok = pcall(function() emu.setInput(1, { [btn] = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { [btn] = on }) end) end
end
local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  local on = (fr % 70) < 5
  press("start", on); press("a", on)
  if fr >= 5400 and not done then done = true; emu.stop(0) end
end, emu.eventType.endFrame)
