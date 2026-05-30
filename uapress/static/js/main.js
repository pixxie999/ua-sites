// 지역 탭 필터
function filterRegion(region) {
  const cards = document.querySelectorAll('.event-card');
  const tabs = document.querySelectorAll('.region-tab');

  tabs.forEach(tab => tab.classList.remove('active'));
  event.currentTarget && event.currentTarget.classList.add('active');

  // 버튼 텍스트로 active 탭 찾기
  tabs.forEach(tab => {
    if (tab.textContent.trim() === region || (region === 'all' && tab.textContent.trim() === '전체')) {
      tab.classList.add('active');
    }
  });

  cards.forEach(card => {
    if (region === 'all' || card.dataset.region === region) {
      card.style.display = '';
    } else {
      card.style.display = 'none';
    }
  });
}

// Fuse.js 검색
(function () {
  let fuse = null;

  async function loadIndex() {
    if (fuse) return;
    try {
      const res = await fetch('/search-index.json');
      const data = await res.json();
      fuse = new Fuse(data.events, {
        keys: ['title', 'region', 'category', 'tags', 'place'],
        threshold: 0.4,
        minMatchCharLength: 2,
      });
    } catch (e) {
      console.warn('검색 인덱스 로드 실패', e);
    }
  }

  const searchInput = document.getElementById('search-input');
  const searchResults = document.getElementById('search-results');

  if (searchInput) {
    searchInput.addEventListener('focus', loadIndex);
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.trim();
      if (!fuse || q.length < 2) {
        searchResults.innerHTML = '';
        return;
      }
      const results = fuse.search(q, { limit: 8 });
      searchResults.innerHTML = results.map(({ item }) => `
        <a href="${item.url}" class="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 transition">
          <div class="flex-1 min-w-0">
            <p class="font-medium text-sm text-gray-900 truncate">${item.title}</p>
            <p class="text-xs text-gray-400">${item.region} · ${item.category} · ${item.start_date_fmt}</p>
          </div>
          ${item.is_free ? '<span class="text-green-600 text-xs font-bold shrink-0">무료</span>' : ''}
        </a>
      `).join('');
    });
  }

  // 모달 바깥 클릭 시 닫기
  const modal = document.getElementById('search-modal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });
  }

  // ESC 키로 모달 닫기
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal) modal.classList.add('hidden');
  });
})();
