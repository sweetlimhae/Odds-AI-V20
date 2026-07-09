
const sportEl = document.getElementById("sport");
const minutesEl = document.getElementById("minutes");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");

document.getElementById("gamesBtn").addEventListener("click", loadGames);
document.getElementById("analyzeBtn").addEventListener("click", analyze);

function params() {
  return `sport=${encodeURIComponent(sportEl.value)}&minutes=${encodeURIComponent(minutesEl.value)}`;
}

function setStatus(text) {
  statusEl.innerHTML = text ? `<div class="notice">${text}</div>` : "";
}

function n(v, fallback = 0) {
  const x = Number(v);
  return Number.isFinite(x) ? x : fallback;
}

function riskLabel(risk) {
  if (risk === "low") return "낮음";
  if (risk === "medium") return "보통";
  if (risk === "high") return "높음";
  return risk || "-";
}

function decisionBadge(decision) {
  if (decision === "BET") return `<span class="badge bet">BET</span>`;
  if (decision === "WATCH") return `<span class="badge watch">WATCH</span>`;
  return `<span class="badge no">NO BET</span>`;
}

function rankIcon(i) {
  if (i === 0) return "🥇";
  if (i === 1) return "🥈";
  if (i === 2) return "🥉";
  return `#${i + 1}`;
}

function confidenceBar(score) {
  score = Math.max(0, Math.min(100, n(score)));
  return `
    <div class="meter"><div class="meter-fill" style="width:${score}%"></div></div>
    <small>AI 신뢰도 ${score}%</small>
  `;
}

function stakeGuide(p) {
  const k = n(p.kelly);
  if (p.risk === "high") return "No Bet 또는 관찰";
  if (k >= 10) return "실전 추천 비중 5~8%";
  if (k >= 5) return "실전 추천 비중 3~5%";
  if (k >= 1) return "실전 추천 비중 1~2%";
  return "소액 또는 관찰";
}

function aiComment(p) {
  const comments = [];
  if (n(p.drop_rate) >= 3) comments.push("배당 하락");
  if (n(p.sharp_score) >= 25) comments.push("Sharp Money");
  if (n(p.steam_score) >= 10) comments.push("Steam Move");
  if (n(p.clv_score) >= 14) comments.push("CLV 기대");
  if (n(p.value_score) >= 8) comments.push("시장 평균 대비 가치");
  if (n(p.ev) >= 5) comments.push("EV 우수");
  else if (n(p.ev) > 0) comments.push("EV 양호");
  if (n(p.kelly) >= 5) comments.push("Kelly 적정");
  if (p.risk === "low") comments.push("위험도 낮음");
  return comments.length ? comments.join(" · ") : "관찰 필요";
}

function renderSummary(summary) {
  if (!summary) return "";
  return `
    <article class="card highlight">
      <h2>오늘 분석 요약</h2>
      <div class="summary-grid">
        <div><small>분석픽</small><b>${summary.total_picks ?? 0}</b></div>
        <div><small>추천조합</small><b>${summary.recommendation_count ?? 0}</b></div>
        <div><small>제외경기</small><b>${summary.excluded_count ?? 0}</b></div>
        <div><small>최고신뢰도</small><b>${summary.top_confidence ?? 0}%</b></div>
        <div><small>평균EV</small><b>${summary.avg_ev ?? 0}%</b></div>
        <div><small>시간필터</small><b>${summary.time_filter || "10~720분"}</b></div>
      </div>
      <p class="reason">${summary.message || ""}</p>
    </article>
  `;
}

function renderGameHeader(game) {
  return `
    <div class="game-head">
      <div>
        <div class="tag">${(game.sport || "").toUpperCase()} · ${game.country || "-"} · ${game.league || "-"}</div>
        <h2>${game.home || "-"} <span>vs</span> ${game.away || "-"}</h2>
      </div>
      <div class="timebox">
        <b>${game.kst_time || "-"}</b>
        <small>시작까지 ${game.start_in_minutes ?? "-"}분</small>
      </div>
    </div>
  `;
}

function renderGames(games, excluded) {
  if ((!games || games.length === 0) && (!excluded || excluded.length === 0)) {
    resultsEl.innerHTML = "<div class='card'>조건에 맞는 경기가 없습니다.</div>";
    return;
  }

  const gamesHtml = (games || []).map(game => `
    <article class="card">
      ${renderGameHeader(game)}
      <div class="market-table">
        <div class="row head">
          <span>마켓</span><span>픽</span><span>현재</span><span>초기</span><span>Pinnacle</span><span>시장평균</span><span>북메이커</span>
        </div>
        ${(game.markets || []).map(m => `
          <div class="row">
            <span>${m.type || "-"}</span>
            <span><b>${m.pick || "-"}</b></span>
            <span>${m.odds ?? "-"}</span>
            <span>${m.open_odds ?? "-"}</span>
            <span>${m.pinnacle_odds ?? "-"}</span>
            <span>${m.market_avg ?? "-"}</span>
            <span>${m.bookmaker || "-"}</span>
          </div>
        `).join("")}
      </div>
    </article>
  `).join("");

  resultsEl.innerHTML = gamesHtml + renderExcluded(excluded);
}

async function loadGames() {
  try {
    setStatus("오늘 경기 불러오는 중...");
    resultsEl.innerHTML = "<div class='card'>불러오는 중...</div>";
    const res = await fetch(`/api/live-games?${params()}`);
    const data = await res.json();
    setStatus(`${data.notice || ""} / 정상 ${data.count || 0}경기 / 제외 ${data.excluded_count || 0}건`);
    renderGames(data.games, data.excluded);
  } catch (err) {
    console.error(err);
    resultsEl.innerHTML = "<div class='card danger'>경기를 불러오지 못했습니다.</div>";
  }
}

function renderPick(p, i) {
  const confidence = p.confidence ?? p.score ?? 0;
  return `
    <div class="pick">
      <div class="rank">${rankIcon(i)} 추천순위 ${i + 1} ${decisionBadge(p.decision)} <span class="ai-icon">${p.confidence_icon || ""}</span></div>
      ${p.pattern_tag ? `<div class="sharp-tag">${p.pattern_tag}</div>` : ""}
      <div class="tag">${(p.sport || "").toUpperCase()} · ${p.country || "-"} · ${p.league || "-"} · ${p.type || ""} · 위험도 ${riskLabel(p.risk)}</div>
      <h3>${p.home || "-"} <span>vs</span> ${p.away || "-"}</h3>
      <p class="time">KST ${p.kst_time || "-"} / 시작까지 ${p.start_in_minutes ?? "-"}분</p>
      ${confidenceBar(confidence)}
      <p><b>추천: ${p.pick || "-"}</b></p>
      <p>등급: <b>${p.grade || "-"}</b></p>
      <div class="summary-grid">
        <div><small>현재배당</small><b>${p.odds ?? "-"}</b></div>
        <div><small>초기배당</small><b>${p.open_odds ?? "-"}</b></div>
        <div><small>Pinnacle</small><b>${p.pinnacle_odds ?? "-"}</b></div>
        <div><small>시장평균</small><b>${p.market_avg ?? "-"}</b></div>
        <div><small>하락률</small><b>${p.drop_rate ?? "-"}%</b></div>
        <div><small>AI 예상승률</small><b>${p.ai_probability ?? "-"}%</b></div>
        <div><small>시장확률</small><b>${p.market_probability ?? "-"}%</b></div>
        <div><small>AI Edge</small><b>${p.ai_edge ?? "-"}%</b></div>
        <div><small>AI 점수</small><b>${p.score ?? "-"}</b></div>
        <div><small>Sharp</small><b>${p.sharp_score ?? "-"}점</b></div>
        <div><small>Steam</small><b>${p.steam_score ?? "-"}점</b></div>
        <div><small>CLV</small><b>${p.clv_score ?? "-"}점</b></div>
        <div><small>EV</small><b>${p.ev ?? "-"}%</b></div>
        <div><small>Kelly</small><b>${p.kelly ?? "-"}%</b></div>
      </div>
      <p class="reason">${(p.reasons || []).join(" · ")}</p>
      <p class="reason">AI 의견: ${aiComment(p)}</p>
      <p class="reason">배팅금액 가이드: ${stakeGuide(p)}</p>
    </div>
  `;
}

function renderCombos(combos) {
  if (!combos || combos.length === 0) {
    return `<article class="card danger"><h2>No Bet</h2><p>현재 조건에서는 추천 조합이 없습니다.</p></article>`;
  }

  return combos.map((combo, comboIndex) => `
    <article class="card highlight">
      <h2>${rankIcon(comboIndex)} ${combo.type || "추천 조합"}</h2>
      <div class="summary-grid">
        <div><small>폴더수</small><b>${combo.folder_size ?? (combo.picks || []).length}</b></div>
        <div><small>총배당</small><b>${combo.total_odds ?? "-"}</b></div>
        <div><small>평균점수</small><b>${combo.avg_score ?? "-"}</b></div>
        <div><small>평균신뢰도</small><b>${combo.avg_confidence ?? "-"}%</b></div>
        <div><small>평균EV</small><b>${combo.avg_ev ?? "-"}%</b></div>
        <div><small>평균Kelly</small><b>${combo.avg_kelly ?? "-"}%</b></div>
      </div>
      ${(combo.picks || []).map((p, i) => renderPick(p, i)).join("")}
    </article>
  `).join("");
}

function renderTopPicks(topPicks) {
  if (!topPicks || topPicks.length === 0) return "";
  return `<article class="card"><h2>단일픽 TOP 10</h2>${topPicks.slice(0, 10).map((p, i) => renderPick(p, i)).join("")}</article>`;
}

function renderExcluded(excluded) {
  if (!excluded || excluded.length === 0) return "";
  return `
    <article class="card danger">
      <h2>제외 경기</h2>
      <div class="market-table">
        <div class="row head"><span>종목</span><span>리그</span><span>경기</span><span>마켓/픽</span><span>제외 이유</span></div>
        ${excluded.slice(0, 30).map(g => `
          <div class="row">
            <span>${g.sport || "-"}</span>
            <span>${g.league || "-"}</span>
            <span>${g.game || "-"}</span>
            <span>${g.type || "-"} / ${g.pick || "-"}</span>
            <span>${g.reason || ""}</span>
          </div>
        `).join("")}
      </div>
    </article>
  `;
}

async function analyze() {
  try {
    setStatus("AI 분석 중...");
    resultsEl.innerHTML = "<div class='card'>AI 분석 중...</div>";
    const res = await fetch(`/api/recommendations?${params()}`);
    const data = await res.json();
    const combos = data.combos || data.recommendations || [];
    setStatus(`${data.notice || "AI 분석 완료"} / 제외 ${data.summary?.excluded_count || 0}건`);
    resultsEl.innerHTML =
      renderSummary(data.summary) +
      renderCombos(combos) +
      renderTopPicks(data.top_picks) +
      renderExcluded(data.excluded);
  } catch (err) {
    console.error(err);
    resultsEl.innerHTML = "<div class='card danger'>AI 분석 실패</div>";
  }
}
