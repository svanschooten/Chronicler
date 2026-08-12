const { createApp, ref, onMounted } = Vue;

const app = createApp({
    setup() {
        const chronicles = ref([]);
        const config = ref(null);
        const status = ref('Initializing...');
        const newChronicleTitle = ref('');
        const showCreateModal = ref(false);
        const selectedChronicle = ref(null);
        const selectedFile = ref(null);
        const isUploading = ref(false);

        const fetchConfig = async () => {
            try {
                const response = await fetch('/config');
                config.value = await response.json();
                status.value = 'Connecting to Chronicler Server...';
                await fetchChronicles();
            } catch (e) {
                status.value = 'Error fetching config: ' + e.message;
            }
        };

        const rpcCall = async (service, method, params = {}) => {
            if (!config.value) return;

            // Same-origin proxy route: the web client injects the API key server-side,
            // so the browser never holds or sends it.
            const url = `/api/${service}/${method}`;
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(params)
                });

                if (!response.ok) {
                    throw new Error(`RPC Error: ${response.statusText}`);
                }

                return await response.json();
            } catch (e) {
                console.error(e);
                throw e;
            }
        };

        const fetchChronicles = async () => {
            try {
                const result = await rpcCall('chronicle', 'list_chronicles');
                chronicles.value = result;
                status.value = 'Connected';
            } catch (e) {
                status.value = 'Error fetching chronicles: ' + e.message;
            }
        };

        const createChronicle = async () => {
            if (!newChronicleTitle.value) return;
            try {
                await rpcCall('chronicle', 'create_chronicle', { title: newChronicleTitle.value });
                newChronicleTitle.value = '';
                showCreateModal.value = false;
                await fetchChronicles();
            } catch (e) {
                alert('Error creating chronicle: ' + e.message);
            }
        };

        const handleFileChange = (event) => {
            selectedFile.value = event.target.files[0];
        };

        const uploadAndImport = async () => {
            if (!selectedFile.value || !selectedChronicle.value) return;
            
            isUploading.value = true;
            status.value = 'Uploading file...';
            
            try {
                // 1. Upload file (same-origin proxy - see rpcCall)
                const formData = new FormData();
                formData.append('file', selectedFile.value);

                const uploadResponse = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                
                if (!uploadResponse.ok) {
                    throw new Error(`Upload failed: ${uploadResponse.statusText}`);
                }
                
                const uploadResult = await uploadResponse.json();
                const filePath = uploadResult.file_path;
                
                // 2. Queue import
                status.value = 'Queuing import...';
                await rpcCall('task', 'queue_import', {
                    chronicle_id: selectedChronicle.value.id,
                    file_path: filePath
                });
                
                status.value = 'Import queued successfully';
                selectedFile.value = null;
                selectedChronicle.value = null;
            } catch (e) {
                status.value = 'Error: ' + e.message;
                alert('Error: ' + e.message);
            } finally {
                isUploading.value = false;
            }
        };

        onMounted(fetchConfig);

        return {
            chronicles,
            config,
            status,
            newChronicleTitle,
            showCreateModal,
            selectedChronicle,
            selectedFile,
            isUploading,
            createChronicle,
            handleFileChange,
            uploadAndImport
        };
    }
});

app.mount('#app');
