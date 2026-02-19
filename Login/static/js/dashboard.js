// Dashboard JavaScript

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeCharts();
    initializeCircularProgress();
    animateWellnessBars();
});

// Initialize Mood Trend Chart
function initializeCharts() {
    const ctx = document.getElementById('moodChart');
    if (!ctx) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
            datasets: [{
                label: 'Wellness Score',
                data: [58, 62, 68, 73],
                borderColor: '#6B9AC4',
                backgroundColor: 'rgba(107, 154, 196, 0.1)',
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointRadius: 6,
                pointBackgroundColor: '#6B9AC4',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 3,
                pointHoverRadius: 8
            },
            {
                label: 'Mood Score',
                data: [45, 52, 58, 65],
                borderColor: '#E8A87C',
                backgroundColor: 'rgba(232, 168, 124, 0.1)',
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointRadius: 6,
                pointBackgroundColor: '#E8A87C',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 3,
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 20,
                        font: {
                            family: "'Plus Jakarta Sans', sans-serif",
                            size: 12,
                            weight: '600'
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 31, 54, 0.95)',
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: {
                        family: "'Plus Jakarta Sans', sans-serif",
                        size: 13,
                        weight: '600'
                    },
                    bodyFont: {
                        family: "'Plus Jakarta Sans', sans-serif",
                        size: 12
                    },
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.parsed.y + '%';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: {
                        color: '#F0F3F7',
                        drawBorder: false
                    },
                    ticks: {
                        font: {
                            family: "'Plus Jakarta Sans', sans-serif",
                            size: 11
                        },
                        color: '#9AA5B9',
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                },
                x: {
                    grid: {
                        display: false,
                        drawBorder: false
                    },
                    ticks: {
                        font: {
                            family: "'Plus Jakarta Sans', sans-serif",
                            size: 11
                        },
                        color: '#9AA5B9'
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
}

// Initialize Circular Progress
function initializeCircularProgress() {
    const progressElement = document.querySelector('.circular-progress');
    if (!progressElement) return;
    
    const progress = parseInt(progressElement.dataset.progress);
    const circle = progressElement.querySelector('.progress-ring-fill');
    const radius = 60;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (progress / 100) * circumference;
    
    circle.style.strokeDasharray = `${circumference} ${circumference}`;
    circle.style.strokeDashoffset = circumference;
    
    // Animate
    setTimeout(() => {
        circle.style.strokeDashoffset = offset;
    }, 100);
}

// Animate Wellness Bars
function animateWellnessBars() {
    const bars = document.querySelectorAll('.wellness-bar');
    bars.forEach((bar, index) => {
        const width = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.width = width;
        }, 200 + (index * 100));
    });
}

// Show MSE Report Modal
function showMSEReport(sessionId) {
    const modal = document.getElementById('mseModal');
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
    
    // In a real implementation, you would fetch the actual session data here
    // For now, we're showing the hardcoded report
}

// Close MSE Report Modal
function closeMSEReport() {
    const modal = document.getElementById('mseModal');
    modal.classList.remove('show');
    document.body.style.overflow = 'auto';
}

// Close modal when clicking outside
document.addEventListener('click', function(event) {
    const modal = document.getElementById('mseModal');
    if (event.target === modal) {
        closeMSEReport();
    }
});

// Close modal with Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeMSEReport();
    }
});

// Download Report Function
function downloadReport() {
    // In a real implementation, this would generate and download a PDF
    alert('Report download functionality will be implemented with backend integration.');
    
    // Example implementation:
    // const reportContent = document.querySelector('.mse-report').innerHTML;
    // generatePDF(reportContent);
}

// Show Emergency Resources
function showEmergencyResources() {
    const resources = `
Emergency Mental Health Resources:

🆘 National Suicide Prevention Lifeline
📞 988 (24/7 Support)

🏥 Crisis Text Line
📱 Text HOME to 741741

🌐 International Association for Suicide Prevention
🔗 https://www.iasp.info/resources/Crisis_Centres/

💚 Your campus counseling center is also available for immediate support.

Remember: You are not alone, and help is always available.
    `;
    
    alert(resources);
    
    // In a real implementation, this would open a modal with formatted resources
}

// Smooth Scroll for Navigation
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', function(e) {
        const href = this.getAttribute('href');
        if (href.startsWith('#')) {
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
        
        // Update active state
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        this.classList.add('active');
    });
});

// Auto-hide alert banner after 5 seconds
setTimeout(() => {
    const alert = document.querySelector('.alert-banner');
    if (alert) {
        alert.style.animation = 'fadeOut 0.3s ease';
        setTimeout(() => {
            alert.remove();
        }, 300);
    }
}, 5000);

// Add fade out animation
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeOut {
        from { opacity: 1; transform: translateY(0); }
        to { opacity: 0; transform: translateY(-10px); }
    }
`;
document.head.appendChild(style);