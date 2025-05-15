document.addEventListener("DOMContentLoaded", () => {

    function loadImage(img) {
        return new Promise((resolve, reject) => {
        img.onload = () => resolve(img);
        img.onerror = () => reject(img);
        img.src = img.dataset.src;
        });
    }

    async function loadAllImages() {
        const images = [...document.querySelectorAll('img[data-src]')];
        const promises = images.map(img => 
        loadImage(img)
            .then(() => img.removeAttribute('data-src'))
            .catch(() => console.error('Erro ao carregar imagem:', img.dataset.src))
        );
        await Promise.all(promises);
    }

    loadAllImages();

    function sortList(descending) {
        const listItems = Array.from(chapterList.querySelectorAll('a')); // Pega todos os itens <li> da lista
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



    const favoriteBtn = document.getElementById('favorite-btn');
    
    if (favoriteBtn) {
        // Adiciona o evento de clique ao botão
        favoriteBtn.addEventListener('click', () => {
            // URL para a requisição
            const url = '/manga/'+manga_id+'/favorite'; // Exemplo de URL, altere conforme necessário
            //Realiza a requisição usando Fetch API
            fetch(url, {
                method: 'GET',
            })
            .then(response => {
                if (response.ok){
                    return response.json();
                }
                else{
                    return {"status":"Failed","message":"something fail."}
                }
                }).then(data =>{
                if (data.status == "success" ){
                    if (data.message == "added"){
                        favoriteBtn.innerHTML = '<i class="fa-regular fa-star"></i>'
                    }
                    else{
                        favoriteBtn.innerHTML = '<i class="fa-solid fa-star"></i>'
                    }
                }
            })

        });
    }
    const dropBtn = document.getElementById("drop-btn");
    const menuView = document.getElementById("menu-view");

    if (dropBtn && menuView) {
        dropBtn.addEventListener("click", () => {
            menuView.classList.toggle("active");
        });
    } else {
        console.error("Elemento não encontrado:", { dropBtn, menuView });
    }

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


});