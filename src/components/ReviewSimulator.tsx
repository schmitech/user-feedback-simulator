import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Button } from './ui/button';
import { Badge } from '../components/ui/badge';
import { Star, Pause, Play, Settings, RefreshCcw } from 'lucide-react';
import { Slider } from '../components/ui/slider';

interface Review {
  reviewId: string;
  reviewDateTime: string;
  timestamp: number;
  clothingId: string;
  age: number;
  title: string;
  review: string;
  rating: number;
  recommended: boolean;
  division: string;
  department: string;
  class: string;
}

interface Stats {
  totalProcessed: number;
  avgRating: number;
  recommendedCount: number;
}

const ReviewSimulator: React.FC = () => {
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [currentReview, setCurrentReview] = useState<Review | null>(null);
  const [recentReviews, setRecentReviews] = useState<Review[]>([]);
  const [reviewCache, setReviewCache] = useState<Review[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [stats, setStats] = useState<Stats>({
    totalProcessed: 0,
    avgRating: 0,
    recommendedCount: 0
  });
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [simulationSpeed, setSimulationSpeed] = useState<number>(5000);
  const [ratingFilter, setRatingFilter] = useState<string>('all');
  const [departmentFilter, setDepartmentFilter] = useState<string>('all');
  const API_URL = import.meta.env.VITE_REVIEWS_API_URL
  const SENTIMENT_API_URL = import.meta.env.VITE_SENTIMENT_API_URL

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });
  };
  
  //Fetch reviews from API Gateway
  const fetchReviews = async (batchSize = 20) => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/reviews`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          batchSize,
          ratingFilter,
          departmentFilter
        })
      });
      
      if (!response.ok) throw new Error('Failed to fetch reviews');
      
      const data = await response.json();
      // Extract the reviews array from the response
      const reviews = data.reviews;
      
      if (!Array.isArray(reviews)) {
        console.error('Expected array of reviews but got:', reviews);
        return;
      }

      setReviewCache(prevCache => [...prevCache, ...reviews]);
    } catch (error) {
      console.error('Error fetching reviews:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (reviewCache.length < 10) {
      fetchReviews();
    }
  }, [reviewCache.length, ratingFilter, departmentFilter]);

  const sendToAPI = async (review: Review) => {
    try {
      const response = await fetch(`${SENTIMENT_API_URL}/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          reviews: [{
            ...review,
            reviewDateTime: review.reviewDateTime,
            timestamp: review.timestamp.toString(),
            reviewId: review.reviewId,
            clothingId: review.clothingId,
            department: review.department,
            division: review.division,
            class: review.class,
            rating: review.rating,
            title: review.title,
            review: review.review,
            recommended: review.recommended,
            age: review.age,
            randomBucket: Math.floor(Math.random() * 10)
          }]
        })
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        console.error('API call failed:', errorData);
      }
    } catch (error) {
      console.error('Error sending review:', error);
    }
  };

  const getNextReview = (): Review | null => {
    if (reviewCache.length === 0) {
      console.warn('Review cache empty, fetching more reviews...');
      fetchReviews();
      return null;
    }

    const randomIndex = Math.floor(Math.random() * reviewCache.length);
    const [selectedReview] = reviewCache.splice(randomIndex, 1);
    setReviewCache([...reviewCache]);

    return {
      ...selectedReview,
      timestamp: Date.now()
    };
  };

  const processNewReview = useCallback(() => {
    const reviewWithTimestamp = getNextReview();
    if (!reviewWithTimestamp) return;

    // Move current review to past reviews if it exists
    if (currentReview) {
      setRecentReviews(prevReviews => {
        const updatedReviews = [currentReview, ...prevReviews].filter(r => 
          r.reviewId !== reviewWithTimestamp.reviewId
        ).slice(0, 5);
        return updatedReviews;
      });
    }

    setCurrentReview(reviewWithTimestamp);
    
    // Update stats
    setStats(prev => ({
      totalProcessed: prev.totalProcessed + 1,
      avgRating: ((prev.avgRating * prev.totalProcessed) + reviewWithTimestamp.rating) / (prev.totalProcessed + 1),
      recommendedCount: prev.recommendedCount + (reviewWithTimestamp.recommended ? 1 : 0)
    }));

    sendToAPI(reviewWithTimestamp);
  }, [currentReview, getNextReview, sendToAPI]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isSimulating && !isLoading) {
      interval = setInterval(processNewReview, simulationSpeed);
    }
    return () => clearInterval(interval);
  }, [isSimulating, simulationSpeed, isLoading, processNewReview]);

  // Reset recent reviews when simulation stops
  useEffect(() => {
    if (!isSimulating) {
      setRecentReviews([]);
    }
  }, [isSimulating]);

  const renderStars = (rating: number) => {
    return [...Array(5)].map((_, index) => (
      <Star
        key={index}
        className={`w-4 h-4 ${index < rating ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'}`}
      />
    ));
  };

  return (
    <div className="p-4 max-w-4xl mx-auto space-y-4">
      <Card className="bg-white shadow-lg">
        <CardHeader>
          <CardTitle className="flex justify-between items-center">
            <span>Live Customer Review Simulator</span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setReviewCache([]);
                  fetchReviews(20);
                }}
                disabled={isLoading}
              >
                <RefreshCcw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowSettings(!showSettings)}
              >
                <Settings className="h-4 w-4" />
              </Button>
              <Button
                onClick={() => setIsSimulating(!isSimulating)}
                disabled={isLoading || reviewCache.length === 0}
                className={isSimulating ? 'bg-red-500 hover:bg-red-600' : 'bg-green-500 hover:bg-green-600'}
              >
                {isSimulating ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                {isSimulating ? 'Stop Stream' : 'Start Stream'}
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {showSettings && (
            <div className="mb-6 p-4 border rounded-lg bg-gray-50">
              <h3 className="font-semibold mb-4">Simulation Settings</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm mb-2">Review Stream Speed (seconds)</label>
                  <Slider
                    value={[simulationSpeed / 1000]}
                    onValueChange={(value) => setSimulationSpeed(value[0] * 1000)}
                    min={1}
                    max={10}
                    step={1}
                  />
                  <div className="text-sm text-gray-500 mt-1">
                    Current: {simulationSpeed / 1000}s between reviews
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm mb-2">Rating Filter</label>
                    <select
                      className="w-full p-2 border rounded"
                      value={ratingFilter}
                      onChange={(e) => setRatingFilter(e.target.value)}
                    >
                      <option value="all">All Ratings</option>
                      <option value="positive">Positive Only (4-5★)</option>
                      <option value="negative">Negative Only (1-3★)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm mb-2">Department Filter</label>
                    <select
                      className="w-full p-2 border rounded"
                      value={departmentFilter}
                      onChange={(e) => setDepartmentFilter(e.target.value)}
                    >
                      <option value="all">All Departments</option>
                      <option value="Dresses">Dresses</option>
                      <option value="Intimate">Intimate</option>
                      <option value="Bottoms">Bottoms</option>
                      <option value="Tops">Tops</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="p-4 bg-blue-50 rounded-lg">
              <div className="text-sm text-blue-600">Reviews Streamed</div>
              <div className="text-2xl font-bold">{stats.totalProcessed}</div>
            </div>
            <div className="p-4 bg-green-50 rounded-lg">
              <div className="text-sm text-green-600">Average Rating</div>
              <div className="text-2xl font-bold">{stats.avgRating.toFixed(1)}</div>
            </div>
            <div className="p-4 bg-purple-50 rounded-lg">
              <div className="text-sm text-purple-600">Cache Size</div>
              <div className="text-2xl font-bold">{reviewCache.length}</div>
            </div>
          </div>

          {currentReview && (
            <div className="mb-6 p-4 border rounded-lg bg-gray-50">
              <div className="text-lg font-semibold mb-2">Current Review</div>
              <div className="flex items-center gap-2 mb-2">
                {renderStars(currentReview.rating)}
                <Badge variant={currentReview.recommended ? "success" : "destructive"}>
                  {currentReview.recommended ? "Recommended" : "Not Recommended"}
                </Badge>
              </div>
              <p className="text-gray-700">{currentReview.review}</p>
              <div className="text-sm text-gray-500 mt-2 flex justify-between items-center">
                <span>Department: {currentReview.department} | Division: {currentReview.division} | Age: {currentReview.age}</span>
                <span className="font-bold">{formatDate(currentReview.reviewDateTime)}</span>
              </div>
            </div>
          )}

          <div>
            <div className="text-lg font-semibold mb-2">Past Reviews</div>
            <div className="space-y-3">
              {recentReviews.map((review) => (
                <div key={review.reviewId} className="p-3 border rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    {renderStars(review.rating)}
                  </div>
                  <p className="text-sm text-gray-700">{review.review}</p>
                  <div className="text-xs text-gray-500 mt-1 flex justify-between items-center">
                    <span>Department: {review.department}</span>
                    <span className="font-bold">{formatDate(review.reviewDateTime)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ReviewSimulator;