import React, { useState } from 'react';
import { PdfPasswordModal } from './PdfPasswordModal';
import { useAppContext } from '../context/AppContext';

export const StatementUploader: React.FC = () => {
    const { user } = useAppContext();
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const uploadFile = async (file: File, password?: string) => {
        setIsUploading(true);
        setError(null);
        setShowPasswordModal(false);

        try {
            // 1. Get the authenticated user ID
            if (!user.userId) throw new Error("You must be logged in to upload statements.");

            // 2. Package everything into FormData
            const formData = new FormData();
            formData.append('file', file);
            formData.append('user_id', user.userId);
            if (password) {
                formData.append('password', password);
            }
            formData.append('account_name', 'My Uploaded Account'); // Or get this from a text input

            // 3. Send to FastAPI
            const response = await fetch('http://localhost:8000/api/statement/upload', {
                method: 'POST',
                body: formData, // Browser automatically sets Content-Type to multipart/form-data
            });

            const result = await response.json();

            if (!response.ok) {
                const errorMsg = typeof result.detail === 'object' && result.detail?.message 
                    ? result.detail.message 
                    : (result.detail || "Upload failed");
                throw new Error(errorMsg);
            }

            alert(`Success! Imported ${result.inserted_count} transactions.`);
            setSelectedFile(null);

        } catch (err: any) {
            console.error(err);
            setError(err.message);
            // Re-open modal if password was wrong and file is PDF
            if (err.message.includes("password") && (file.type === 'application/pdf' || file.name.endsWith('.pdf'))) {
                setShowPasswordModal(true);
            }
        } finally {
            setIsUploading(false);
        }
    };

    // Triggered when user selects a file from input
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            const file = e.target.files[0];
            setSelectedFile(file);

            // If PDF, prompt for password immediately
            if (file.type === 'application/pdf' || file.name.endsWith('.pdf')) {
                setShowPasswordModal(true);
            } else {
                // Otherwise (CSV, plain text, etc.), upload immediately
                uploadFile(file);
            }
        }
    };

    // Triggered when the user submits the password in the modal
    const handlePasswordSubmit = async (password: string) => {
        if (!selectedFile) return;
        await uploadFile(selectedFile, password);
    };

    return (
        <div className="p-6 bg-surface-container rounded-2xl">
            <h2 className="text-xl font-bold mb-4">Upload Bank Statement</h2>

            <input
                type="file"
                accept=".pdf,.csv"
                onChange={handleFileChange}
                disabled={isUploading}
                className="block w-full text-sm text-outline file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20"
            />

            {isUploading && <p className="mt-4 text-primary animate-pulse">Processing statement (this may take a minute)...</p>}
            {error && <p className="mt-4 text-error font-bold">{error}</p>}

            {showPasswordModal && selectedFile && (
                <PdfPasswordModal
                    fileName={selectedFile.name}
                    isWrongPassword={!!error}
                    onSubmit={handlePasswordSubmit}
                    onCancel={() => {
                        setShowPasswordModal(false);
                        setSelectedFile(null);
                    }}
                />
            )}
        </div>
    );
};