-- dump_setbox_vram.lua : 수동 세팅 X메뉴가 뜬 순간의 VRAM 전체 덤프.
--   목적(docs/20 §Claude 통합 계획 step1~2): 공유 타일256 페이지에서 파츠/옵션/팀/인물명이
--   실제 쓰는 타일 오프셋을 실측 → X메뉴 한글 14음절용 "미사용 예약 슬롯" 안전 확보.
--   사용법(맥): Mesen out/wgp2_kr.smc scripts/lua/capture/dump_setbox_vram.lua →
--     개러지 수동 세팅 진입 → X로 팝업 메뉴 연 상태에서 **L 버튼(왼쪽 숄더)을 누르고 있기**.
--     그 프레임의 VRAM 64KB가 tmp/trace/setbox_vram.bin 에 저장됨(누를 때마다 덮어씀).
local OUT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/setbox_vram.bin"
local INFO = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/setbox_vram.txt"
local dumped_at = -999

local function held(btn)
  local ok, st = pcall(function() return emu.getInput(0) end)
  if ok and type(st)=="table" then return st[btn] end
  return false
end

local function dumpVram()
  local f = io.open(OUT, "wb"); if not f then return false end
  local t = {}
  for i = 0, 0xFFFF do
    t[#t+1] = string.char(emu.read(i, emu.memType.snesVideoRam) & 0xFF)
    if #t == 4096 then f:write(table.concat(t)); t = {} end
  end
  if #t > 0 then f:write(table.concat(t)) end
  f:close()
  local st = emu.getState()
  local lf = io.open(INFO, "w")
  if lf then
    lf:write(string.format("frame=%d  VRAM 64KB 덤프 완료\n", st["frameCount"] or 0))
    lf:write("타일256 페이지 = VRAM byte 0x1000~0x2400 (320타일 2bpp)\n")
    lf:write("BG 타일맵에서 참조 타일번호 수집 → 오프셋 = 타일번호-256\n")
    lf:close()
  end
  return true
end

emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"] or 0
  if held("l") or held("L") then
    if fr - dumped_at > 30 then
      if dumpVram() then dumped_at = fr; emu.displayMessage("setbox", "VRAM 덤프됨 f="..fr) end
    end
  end
end, emu.eventType.endFrame)

emu.displayMessage("setbox", "수동세팅 X메뉴 열고 L 버튼 누르기 → VRAM 덤프")
