document.addEventListener("DOMContentLoaded", () => {
    const dropBtn = document.getElementById("drop-btn");
    const menuView = document.getElementById("menu-view");

    if (dropBtn && menuView) {
        dropBtn.addEventListener("click", () => {
            menuView.classList.toggle("active");
        });
    } else {
        console.error("Elemento não encontrado:", { dropBtn, menuView });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    const filterButton = document.getElementById('chapter-filter');
    const icon = filterButton.querySelector('i');
    const chapterList = document.querySelector('.chapter-list ul'); // Pega a lista de capítulos (ul)

    filterButton.addEventListener('click', function() {
        // Alterna o ícone
        if (icon.classList.contains('fa-arrow-up-wide-short')) {
            icon.classList.remove('fa-arrow-up-wide-short');
            icon.classList.add('fa-arrow-down-wide-short');
            // Ordena a lista de capítulos de forma crescente
            sortList(false);
        } else {
            icon.classList.remove('fa-arrow-down-wide-short');
            icon.classList.add('fa-arrow-up-wide-short');
            // Ordena a lista de capítulos de forma decrescente
            sortList(true);
        }
    });

    function sortList(descending) {
        const listItems = Array.from(chapterList.querySelectorAll('li')); // Pega todos os itens <li> da lista
        listItems.sort((a, b) => {
            // Extraímos o número do capítulo, garantindo que seja tratado como um número
            const capA = parseFloat(a.querySelector('p').textContent.replace('Capítulo ', '').trim());
            const capB = parseFloat(b.querySelector('p').textContent.replace('Capítulo ', '').trim());

            // Agora a comparação é feita corretamente com números decimais
            return descending ? capB - capA : capA - capB;
        });

        // Reordena os itens no DOM
        listItems.forEach(item => chapterList.appendChild(item));
    }
});