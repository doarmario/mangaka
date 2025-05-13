document.addEventListener("DOMContentLoaded", function() {
    const modeSelect = document.getElementById("scrollToggle"); // O toggle de "scroll" ou "page"
    const leitorContainer = document.getElementById("leitor");
    const prevButton = document.getElementById("changeprev");
    const nextButton = document.getElementById("changenext");
    let currentPageIndex = 0;
    let totalImages = pages.length; // Usando a variável `data.pages` que foi passada pelo Jinja2
    let currentMode = localStorage.getItem("mode") || "páginas"; // Recupera o modo armazenado no localStorage ou define como "páginas"
    let loadedPages = {}; // Armazena as páginas já carregadas
    let imageCache = {}; // Armazena as imagens pré-carregadas


    // Define o modo inicial no toggle
    modeSelect.checked = (currentMode === "scroll");

    // Atualiza o valor no localStorage e o modo de leitura sempre que houver uma mudança no toggle
    modeSelect.addEventListener("change", function() {
        currentMode = modeSelect.checked ? "scroll" : "páginas"; // Alterna entre scroll e páginas
        localStorage.setItem("mode", currentMode);
        updateMode();
    });

    // Inicializa o modo de leitura
    updateMode();

    prevButton.addEventListener("click", function() {
        changePage(-1);
    });

    nextButton.addEventListener("click", function() {
        changePage(1);
    });

    function changePage(direction) {
        currentPageIndex += direction;
        if (currentPageIndex < 0) {
            currentPageIndex = 0;
        } else if (currentPageIndex >= totalImages) {
            currentPageIndex = totalImages - 1;
        }

        preloadImages();
        updateMode();

        // Verifica se a página atual é a última página
        if (currentPageIndex === totalImages - 1) {
            setRead();
        }
    }

    function setRead() {
        // Esta função pode fazer algo quando o usuário chegar na última página
        // Constrói a URL para a requisição
        const urlEspecifica = "/cap/"+cap+"/readed";

        // Faz a requisição AJAX para a URL específica
        fetch(urlEspecifica, {
            method: 'GET'
            // Adicione quaisquer dados ou corpo da requisição, se necessário
        })
        .then(response => {
            // Manipula a resposta da requisição
            //if (response.ok) {
            //    console.log("lido");
            //} else {
            //    console.error("Erro ao definir como lido", response.status);
            //}
        });
    }

    function updateMode() {
        if (currentMode === "scroll") {
            showScrollMode();
            prevButton.style.display = "none"; // Oculta o botão de página anterior
            nextButton.style.display = "none"; // Oculta o botão de próxima página
            window.addEventListener("scroll", scrollHandler); // Adiciona ouvinte de evento de rolagem
        } else if (currentMode === "páginas") {
            showPageMode();
            prevButton.style.display = "block"; // Exibe o botão de página anterior
            nextButton.style.display = "block"; // Exibe o botão de próxima página
            window.removeEventListener("scroll", scrollHandler); // Remove ouvinte de evento de rolagem
        }
    }

    function showScrollMode() {
        leitorContainer.innerHTML = ""; // Limpa o conteúdo atual

        // Carrega as três primeiras páginas
        for (let i = 0; i < Math.min(3, totalImages); i++) {
            const img = document.createElement("img");
            img.src = pages[i]; // Usando os links de `data.pages` que foram passados como JSON
            leitorContainer.appendChild(img);
            loadedPages[i] = true; // Marca a página como carregada
        }
    }

    function scrollHandler() {
        if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight-600) {
            //console.log("Usuário está próximo do final da página");
    
            // Se estiver próximo do final da página, carrega duas páginas adicionais
            loadNextPages(2);
            setTimeout(() => {}, 1000);
            
            // Verifica se o usuário está no final do capítulo
            if ((window.innerHeight + window.scrollY) >= (document.body.offsetHeight - 100)) {
                setRead();
                setTimeout(() => {}, 1000);
            }
        } else {
            // Pré-carrega as próximas imagens enquanto o usuário rola para baixo
            preloadImages();
            setTimeout(() => {}, 1000);
        }
    }

    function loadNextPages(numPages) {
        let nextPageIndex = currentPageIndex + 1;

        // Carrega as próximas duas páginas que ainda não foram carregadas
        for (let i = 0; i < numPages; i++) {
            while (loadedPages[nextPageIndex]) {
                nextPageIndex++;
            }

            if (nextPageIndex < totalImages) {
                const img = document.createElement("img");
                img.src = pages[nextPageIndex]; // Usando os links de `data.pages`
                leitorContainer.appendChild(img);
                loadedPages[nextPageIndex] = true; // Marca a página como carregada
                nextPageIndex++;
            }
        }
    }

    function preloadImages() {
        const preloadIndex = currentPageIndex + 1;
        if (preloadIndex < totalImages) {
            const nextPageUrl = pages[preloadIndex]; // Usando os links de `data.pages`
            if (!imageCache[nextPageUrl]) {
                const tempImg = new Image();
                tempImg.src = nextPageUrl;
                imageCache[nextPageUrl] = true; // Marca a imagem como pré-carregada
            }
        }
    }

    function showPageMode() {
        leitorContainer.innerHTML = ""; // Limpa o conteúdo atual

        const img = document.createElement("img");
        const currentPageUrl = pages[currentPageIndex]; // Usando os links de `data.pages`
        
        // Verifica se a imagem já foi pré-carregada
        if (imageCache[currentPageUrl]) {
            img.src = currentPageUrl;
            leitorContainer.appendChild(img);
        } else {
            const tempImg = new Image();
            tempImg.src = currentPageUrl;
            tempImg.onload = function() {
                img.src = currentPageUrl;
                leitorContainer.appendChild(img);
                imageCache[currentPageUrl] = true; // Marca a imagem como pré-carregada
            };
        }
        
        preloadImages();
    }
});
